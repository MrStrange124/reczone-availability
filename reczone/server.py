from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx

from reczone.availability import fetch_grid
from reczone.cache import CachingTransport, ResponseCache
from reczone.client import ReczoneClient
from reczone.http import HttpxTransport, build_http_client

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
BOOK_URL = "https://reczone.mcgm.gov.in/sports-complex/book-your-sport"

# RecZone allows 60 requests/minute per caller, and one grid render fans out to
# roughly courts x dates requests. Behind a shared CDN cache that budget is spent
# once per window no matter how many people are looking, so these headers are what
# keep a public deployment from rate-limiting itself. Venue/court/date lists change
# rarely; the grid changes whenever somebody books.
GRID_CACHE = "public, s-maxage=60, stale-while-revalidate=300"
REFERENCE_CACHE = "public, s-maxage=3600, stale-while-revalidate=86400"

# The headers above only help where a shared cache sits in front of us. This one
# is the origin's own one-minute memory, and it is what protects a warm instance
# serving requests the CDN chose not to answer: a repeat grid render inside the
# window costs nothing upstream at all. Deliberately the same window as GRID_CACHE's
# s-maxage, so the origin stops trusting a grid at the same moment the CDN does.
CACHE_TTL = 60.0
RESPONSE_CACHE = ResponseCache(ttl=CACHE_TTL)

# One identifier for the life of the process, not one per request. It rides along
# as a timeslots query param, so a fresh uuid each time would give every read its
# own cache key and the fan-out would never be served from memory. Nothing is ever
# locked or booked under it.
VIEWER_IDENTIFIER = str(uuid.uuid4())


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with build_http_client() as http:
        app.state.http = http
        app.state.http_loop = asyncio.get_running_loop()
        yield


# StaticFiles sends ETag and Last-Modified but no Cache-Control, and with no
# directive at all a browser falls back to heuristic caching -- roughly a tenth of
# the file's age -- and will serve a stale app.css for hours without ever asking.
# "no-cache" does not mean "do not store"; it means "revalidate before use", so the
# ETag still turns the common case into a 304 and a deploy actually reaches people.
REVALIDATE = "no-cache"


class RevalidatingStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers.setdefault("Cache-Control", REVALIDATE)
        return response


app = FastAPI(title="RecZone court sheet", lifespan=lifespan)
app.mount("/static", RevalidatingStaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(httpx.HTTPStatusError)
async def reczone_http_error(request: Request, exc: httpx.HTTPStatusError):
    upstream = exc.response.status_code if exc.response is not None else 502
    if upstream == 429:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "RecZone is rate-limiting right now. Wait a few seconds and check the sheet again."
            },
        )
    return JSONResponse(
        status_code=502,
        content={"detail": f"RecZone returned HTTP {upstream}."},
    )


async def get_client(request: Request) -> ReczoneClient:
    # Async on purpose: FastAPI runs sync dependencies in a worker thread, where
    # _http() would find no running event loop to key its client cache on.
    transport = CachingTransport(HttpxTransport(_http(request.app)), RESPONSE_CACHE)
    return ReczoneClient(transport, identifier=VIEWER_IDENTIFIER)


def _http(app: FastAPI) -> httpx.AsyncClient:
    """One HTTP client per event loop, built on demand.

    Two serverless realities drive this. Runtimes are not obliged to run ASGI
    lifespan events, so trusting lifespan alone would leave app.state.http unset and
    500 every route. And a client's connection pool is bound to the loop that opened
    it, so a host that runs each invocation under its own loop would fail any reused
    client with "Event loop is closed". Keying the cache on the running loop keeps
    connection pooling on a warm instance while staying correct if the loop rotates.
    """
    loop = asyncio.get_running_loop()
    http = getattr(app.state, "http", None)
    if http is None or http.is_closed or getattr(app.state, "http_loop", None) is not loop:
        http = build_http_client()
        app.state.http = http
        app.state.http_loop = loop
    return http


@app.get("/")
def index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html", headers={"Cache-Control": REVALIDATE}
    )


@app.get("/api/complexes")
async def complexes(response: Response, client: ReczoneClient = Depends(get_client)):
    response.headers["Cache-Control"] = REFERENCE_CACHE
    return {"data": await client.complexes()}


@app.get("/api/facilities")
async def facilities(
    complex_id: int,
    response: Response,
    client: ReczoneClient = Depends(get_client),
):
    response.headers["Cache-Control"] = REFERENCE_CACHE
    return {"data": await client.facilities(complex_id)}


@app.get("/api/courts")
async def courts(
    complex_id: int,
    facility_id: int,
    response: Response,
    client: ReczoneClient = Depends(get_client),
):
    response.headers["Cache-Control"] = REFERENCE_CACHE
    return {"data": await client.courts(complex_id, facility_id)}


@app.get("/api/dates")
async def dates(
    complex_id: int,
    facility_id: int,
    court_id: int,
    response: Response,
    client: ReczoneClient = Depends(get_client),
):
    response.headers["Cache-Control"] = REFERENCE_CACHE
    return {"data": await client.dates(complex_id, facility_id, court_id)}


def _parse_court_ids(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    try:
        return [int(part) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="court_ids must be a comma-separated list of court numbers.",
        )


@app.get("/api/grid")
async def grid(
    complex_id: int,
    facility_id: int,
    # Typed as dates so FastAPI rejects junk with a 422. As bare strings these were
    # compared lexically, where "yesterday" sorts after any ISO date and produced a
    # confident but wrong "End date is before start date."
    start: date,
    end: date,
    response: Response,
    court_ids: str | None = Query(default=None),
    client: ReczoneClient = Depends(get_client),
):
    if end < start:
        raise HTTPException(status_code=400, detail="End date is before start date.")
    payload = await fetch_grid(
        client,
        reczone_id=complex_id,
        facility_id=facility_id,
        court_ids=_parse_court_ids(court_ids),
        start=start.isoformat(),
        end=end.isoformat(),
    )
    payload["complex_id"] = complex_id
    payload["facility_id"] = facility_id
    payload["book_url"] = f"{BOOK_URL}?complex={complex_id}&type=1"
    response.headers["Cache-Control"] = GRID_CACHE
    return payload
