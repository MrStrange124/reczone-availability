from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx

from reczone.availability import fetch_grid
from reczone.client import ReczoneClient
from reczone.http import build_http_client
from reczone.http import HttpxTransport

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
BOOK_URL = "https://reczone.mcgm.gov.in/sports-complex/book-your-sport"


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with build_http_client() as http:
        app.state.http = http
        yield


app = FastAPI(title="RecZone court sheet", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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


def get_client(request: Request) -> ReczoneClient:
    return ReczoneClient(HttpxTransport(request.app.state.http))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/complexes")
async def complexes(client: ReczoneClient = Depends(get_client)):
    return {"data": await client.complexes()}


@app.get("/api/facilities")
async def facilities(
    complex_id: int,
    client: ReczoneClient = Depends(get_client),
):
    return {"data": await client.facilities(complex_id)}


@app.get("/api/courts")
async def courts(
    complex_id: int,
    facility_id: int,
    client: ReczoneClient = Depends(get_client),
):
    return {"data": await client.courts(complex_id, facility_id)}


@app.get("/api/dates")
async def dates(
    complex_id: int,
    facility_id: int,
    court_id: int,
    client: ReczoneClient = Depends(get_client),
):
    return {"data": await client.dates(complex_id, facility_id, court_id)}


@app.get("/api/grid")
async def grid(
    complex_id: int,
    facility_id: int,
    start: str,
    end: str,
    court_ids: str | None = Query(default=None),
    client: ReczoneClient = Depends(get_client),
):
    if end < start:
        raise HTTPException(status_code=400, detail="End date is before start date.")
    ids = None
    if court_ids:
        ids = [int(part) for part in court_ids.split(",") if part.strip()]
    payload = await fetch_grid(
        client,
        reczone_id=complex_id,
        facility_id=facility_id,
        court_ids=ids,
        start=start,
        end=end,
    )
    payload["complex_id"] = complex_id
    payload["facility_id"] = facility_id
    payload["book_url"] = f"{BOOK_URL}?complex={complex_id}&type=1"
    return payload
