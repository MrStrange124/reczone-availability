import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx

from reczone.client import ReczoneClient
from reczone.server import (
    CACHE_TTL,
    GRID_CACHE,
    REFERENCE_CACHE,
    RESPONSE_CACHE,
    app,
    get_client,
)


class ScriptedClient:
    async def complexes(self):
        return [{"id": 2, "name": "Shahaji Raje Bhosle Kreeda Sankul, Andheri"}]

    async def facilities(self, reczone_id):
        return [{"id": 2, "name": "Badminton", "slug": "badminton"}]

    async def courts(self, reczone_id, facility_id):
        return [{"id": 1, "name": "Wooden Court 1"}]

    async def dates(self, reczone_id, facility_id, court_id):
        return [
            {
                "month": "August 2026",
                "dates": [
                    {"date": "2026-08-14", "dayOfWeek": "Fri", "day": 14, "isClosed": False},
                ],
            }
        ]

    async def timeslots(self, reczone_id, facility_id, court_id, date):
        return [
            {
                "id": 147,
                "slot": "07:00 PM - 08:00 PM",
                "cost": 450,
                "is_booked": True,
                "is_busy": False,
                "is_reserved": False,
            }
        ]


def test_complexes_endpoint_lists_venues():
    app.dependency_overrides[get_client] = lambda: ScriptedClient()
    try:
        response = TestClient(app).get("/api/complexes")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == 2


def test_home_serves_court_sheet():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert "Court sheet" in response.text


def test_grid_endpoint_returns_classified_slots():
    app.dependency_overrides[get_client] = lambda: ScriptedClient()
    try:
        response = TestClient(app).get(
            "/api/grid",
            params={
                "complex_id": 2,
                "facility_id": 2,
                "start": "2026-08-14",
                "end": "2026-08-14",
                "court_ids": "1",
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["courts"][0]["days"]["2026-08-14"][0]["status"] == "booked"
    assert body["book_url"].endswith("complex=2&type=1")


def test_reczone_rate_limit_returns_429_not_500():
    request = httpx.Request("GET", "https://reczone-admin.mcgm.gov.in/x")
    response = httpx.Response(429, request=request)

    class Limited(ScriptedClient):
        async def courts(self, reczone_id, facility_id):
            raise httpx.HTTPStatusError(
                "429 Too Many Requests", request=request, response=response
            )

    app.dependency_overrides[get_client] = lambda: Limited()
    try:
        result = TestClient(app).get(
            "/api/courts", params={"complex_id": 2, "facility_id": 2}
        )
    finally:
        app.dependency_overrides.clear()
    assert result.status_code == 429
    assert "rate" in result.json()["detail"].lower()


def fake_request(**state):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(**state)))


def test_get_client_builds_transport_when_lifespan_never_ran():
    """Serverless hosts may skip ASGI lifespan, leaving app.state.http unset."""
    client = asyncio.run(get_client(fake_request()))
    assert isinstance(client, ReczoneClient)
    assert not client.transport.inner.http.is_closed


def test_get_client_pools_one_transport_within_an_event_loop():
    request = fake_request()

    async def twice():
        first = await get_client(request)
        second = await get_client(request)
        return first.transport.inner.http, second.transport.inner.http

    first, second = asyncio.run(twice())
    assert first is second


def test_get_client_rebuilds_when_the_event_loop_changed():
    """An httpx client outlives its loop but its pool does not: reusing a client
    built on a closed loop raises "Event loop is closed" on the next request."""
    request = fake_request()

    async def build():
        return (await get_client(request)).transport.inner.http

    first = asyncio.run(build())
    second = asyncio.run(build())  # a fresh loop, as a new invocation may be
    assert first is not second


def test_get_client_reuses_the_open_lifespan_client():
    async def build():
        http = httpx.AsyncClient()
        request = fake_request(http=http, http_loop=asyncio.get_running_loop())
        return (await get_client(request)).transport.inner.http is http

    assert asyncio.run(build())


def test_endpoints_serve_repeat_requests_with_no_lifespan_and_no_override(monkeypatch):
    """The serverless shape end to end: lifespan never runs and FastAPI resolves
    get_client itself, so the threadpool and stale-loop traps are both in play.
    The second request is the one that fails if the client cache is wrong.
    """

    def fake_build_http_client():
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"code": 200, "data": [{"id": 2}]})

        return httpx.AsyncClient(
            base_url="https://reczone-admin.test",
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr("reczone.server.build_http_client", fake_build_http_client)

    client = TestClient(app)  # no `with`, so no lifespan
    for _ in range(3):
        response = client.get("/api/complexes")
        assert response.status_code == 200, response.text
        assert response.json()["data"][0]["id"] == 2


def test_grid_is_cdn_cacheable_to_stay_under_the_upstream_rate_limit():
    app.dependency_overrides[get_client] = lambda: ScriptedClient()
    try:
        response = TestClient(app).get(
            "/api/grid",
            params={
                "complex_id": 2,
                "facility_id": 2,
                "start": "2026-08-14",
                "end": "2026-08-14",
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.headers["cache-control"] == GRID_CACHE


def test_reference_endpoints_cache_longer_than_the_grid():
    app.dependency_overrides[get_client] = lambda: ScriptedClient()
    try:
        response = TestClient(app).get("/api/complexes")
    finally:
        app.dependency_overrides.clear()
    assert response.headers["cache-control"] == REFERENCE_CACHE


def test_the_page_and_its_assets_must_revalidate():
    """Without an explicit directive browsers cache heuristically off Last-Modified,
    which serves a stale app.css for hours after a deploy without ever asking."""
    client = TestClient(app)
    for path in ("/", "/static/app.css", "/static/app.js"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "no-cache" in response.headers.get("cache-control", ""), path


def test_junk_court_ids_are_rejected_rather_than_crashing():
    """court_ids arrives as a raw string and gets int()ed; unguarded that is a 500."""
    app.dependency_overrides[get_client] = lambda: ScriptedClient()
    try:
        response = TestClient(app).get(
            "/api/grid",
            params={
                "complex_id": 2,
                "facility_id": 2,
                "start": "2026-08-14",
                "end": "2026-08-14",
                "court_ids": "1,not-a-court",
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    assert "court" in response.json()["detail"].lower()


def test_a_malformed_date_is_rejected_rather_than_silently_empty():
    """Compared as bare strings, "yesterday" simply matches no date and returns an
    empty grid, which reads to the user as "nothing is open"."""
    app.dependency_overrides[get_client] = lambda: ScriptedClient()
    try:
        response = TestClient(app).get(
            "/api/grid",
            params={
                "complex_id": 2,
                "facility_id": 2,
                "start": "yesterday",
                "end": "2026-08-14",
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_identifier_is_stable_so_timeslot_reads_can_be_cached():
    """ReczoneClient mints a random identifier when it is not given one, and it
    travels as a timeslots query param. A fresh one per request would put every
    read behind its own cache key -- and timeslots is the whole fan-out."""

    async def build():
        first = await get_client(fake_request())
        second = await get_client(fake_request())
        return first.identifier, second.identifier

    first, second = asyncio.run(build())
    assert first == second


def reczone_handler(calls: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if path.endswith("/timeslots"):
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": [
                        {
                            "id": 147,
                            "slot": "07:00 PM - 08:00 PM",
                            "cost": 450,
                            "is_booked": False,
                            "is_busy": False,
                            "is_reserved": False,
                        }
                    ],
                },
            )
        if path.endswith("/dates"):
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": [
                        {
                            "month": "August 2026",
                            "dates": [
                                {
                                    "date": "2026-08-14",
                                    "dayOfWeek": "Fri",
                                    "day": 14,
                                    "isClosed": False,
                                }
                            ],
                        }
                    ],
                },
            )
        if path.endswith("/facility-subtypes"):
            return httpx.Response(
                200, json={"code": 200, "data": [{"id": 1, "name": "Wooden Court 1"}]}
            )
        return httpx.Response(200, json={"code": 200, "data": []})

    return handler


def test_a_repeat_grid_render_costs_nothing_upstream(monkeypatch):
    """The point of the server cache: RecZone allows 60 requests/minute and one
    grid render spends courts x dates of them."""
    calls: list[str] = []

    def fake_build_http_client():
        return httpx.AsyncClient(
            base_url="https://reczone-admin.test",
            transport=httpx.MockTransport(reczone_handler(calls)),
        )

    monkeypatch.setattr("reczone.server.build_http_client", fake_build_http_client)

    client = TestClient(app)
    params = {
        "complex_id": 2,
        "facility_id": 2,
        "start": "2026-08-14",
        "end": "2026-08-14",
    }

    first = client.get("/api/grid", params=params)
    assert first.status_code == 200, first.text
    spent = len(calls)
    assert spent > 0

    second = client.get("/api/grid", params=params)
    assert second.status_code == 200, second.text
    assert len(calls) == spent
    assert second.json() == first.json()


def test_the_cache_lets_go_once_the_window_elapses(monkeypatch):
    calls: list[str] = []

    def fake_build_http_client():
        return httpx.AsyncClient(
            base_url="https://reczone-admin.test",
            transport=httpx.MockTransport(reczone_handler(calls)),
        )

    monkeypatch.setattr("reczone.server.build_http_client", fake_build_http_client)

    now = {"t": 1000.0}
    monkeypatch.setattr(RESPONSE_CACHE, "clock", lambda: now["t"])

    client = TestClient(app)
    params = {
        "complex_id": 2,
        "facility_id": 2,
        "start": "2026-08-14",
        "end": "2026-08-14",
    }

    client.get("/api/grid", params=params)
    spent = len(calls)

    now["t"] += CACHE_TTL - 1
    client.get("/api/grid", params=params)
    assert len(calls) == spent, "still inside the window"

    now["t"] += 2
    client.get("/api/grid", params=params)
    assert len(calls) == spent * 2, "window elapsed, read upstream again"
