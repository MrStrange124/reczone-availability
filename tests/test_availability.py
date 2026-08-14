from reczone.availability import fetch_grid


class ScriptedClient:
    def __init__(self, courts, months, slots):
        self._courts = courts
        self._months = months
        self._slots = slots
        self.timeslot_calls: list[tuple[int, str]] = []

    async def courts(self, reczone_id, facility_id):
        return self._courts

    async def dates(self, reczone_id, facility_id, court_id):
        return self._months

    async def timeslots(self, reczone_id, facility_id, court_id, date):
        self.timeslot_calls.append((court_id, date))
        return self._slots.get((court_id, date), [])


async def test_fetch_grid_skips_closed_days_and_unselected_courts():
    client = ScriptedClient(
        courts=[
            {"id": 1, "name": "Wooden Court 1"},
            {"id": 2, "name": "Wooden Court 2"},
        ],
        months=[
            {
                "month": "August 2026",
                "dates": [
                    {"date": "2026-08-14", "dayOfWeek": "Fri", "day": 14, "isClosed": False},
                    {"date": "2026-08-15", "dayOfWeek": "Sat", "day": 15, "isClosed": True},
                ],
            }
        ],
        slots={
            (1, "2026-08-14"): [
                {
                    "id": 10,
                    "slot": "07:00 PM - 08:00 PM",
                    "cost": 450,
                    "is_booked": False,
                    "is_busy": False,
                    "is_reserved": False,
                }
            ]
        },
    )

    grid = await fetch_grid(
        client,
        reczone_id=2,
        facility_id=2,
        court_ids=[1],
        start="2026-08-14",
        end="2026-08-15",
    )

    assert [court["name"] for court in grid["courts"]] == ["Wooden Court 1"]
    assert client.timeslot_calls == [(1, "2026-08-14")]
    assert grid["courts"][0]["days"]["2026-08-14"][0]["status"] == "free"
    assert grid["courts"][0]["days"]["2026-08-15"][0]["status"] == "closed"
