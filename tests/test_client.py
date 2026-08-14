from reczone.client import ReczoneClient


class FakeTransport:
    def __init__(self, routes: dict[str, dict]):
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    async def get(self, path: str, params: dict | None = None):
        self.calls.append((path, params or {}))
        payload = self.routes.get(path)
        if payload is None:
            raise LookupError(path)
        return payload


async def test_complexes_use_public_reczone_list():
    transport = FakeTransport(
        {
            "/api/v1/bookings/membership-booking/reczones": {
                "code": 200,
                "data": [{"id": 2, "name": "Shahaji Raje Bhosle Kreeda Sankul, Andheri"}],
            }
        }
    )
    client = ReczoneClient(transport)
    complexes = await client.complexes()
    assert complexes[0]["id"] == 2
    assert "Andheri" in complexes[0]["name"]


async def test_timeslots_request_includes_date_and_identifier():
    transport = FakeTransport(
        {
            "/api/v1/general-slot-bookings/reczones/2/facilities/2/facility-subtypes/1/timeslots": {
                "code": 200,
                "data": [{"id": 147, "slot": "07:00 PM - 08:00 PM", "cost": 450, "is_booked": True, "is_busy": False, "is_reserved": False}],
            }
        }
    )
    client = ReczoneClient(transport, identifier="test-user")
    slots = await client.timeslots(2, 2, 1, "2026-08-14")
    assert slots[0]["id"] == 147
    path, params = transport.calls[0]
    assert path.endswith("/facility-subtypes/1/timeslots")
    assert params == {
        "identifier": "test-user",
        "date_of_booking": "2026-08-14",
        "locale": "en",
    }
