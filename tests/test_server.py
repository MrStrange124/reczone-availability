from fastapi.testclient import TestClient
import httpx

from reczone.server import app, get_client


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
