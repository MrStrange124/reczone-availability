from reczone.slots import build_grid, filter_dates, slot_sort_key


def test_morning_slots_sort_before_evening():
    hours = ["07:00 PM - 08:00 PM", "05:00 AM - 06:00 AM", "06:00 AM - 07:00 AM"]
    assert sorted(hours, key=slot_sort_key) == [
        "05:00 AM - 06:00 AM",
        "06:00 AM - 07:00 AM",
        "07:00 PM - 08:00 PM",
    ]


def test_filter_dates_keeps_inclusive_range_across_months():
    months = [
        {
            "month": "August 2026",
            "dates": [
                {"date": "2026-08-14", "dayOfWeek": "Fri", "day": 14, "isClosed": False},
                {"date": "2026-08-15", "dayOfWeek": "Sat", "day": 15, "isClosed": False},
            ],
        },
        {
            "month": "September 2026",
            "dates": [
                {"date": "2026-09-01", "dayOfWeek": "Tue", "day": 1, "isClosed": False},
            ],
        },
    ]
    selected = filter_dates(months, "2026-08-15", "2026-09-01")
    assert [day["date"] for day in selected] == ["2026-08-15", "2026-09-01"]


def test_grid_places_classified_slots_on_court_and_date():
    courts = [{"id": 1, "name": "Wooden Court 1", "dimension": "968 Sq ft"}]
    dates = [
        {"date": "2026-08-14", "dayOfWeek": "Fri", "day": 14, "isClosed": False},
        {"date": "2026-08-15", "dayOfWeek": "Sat", "day": 15, "isClosed": True},
    ]
    slots = {
        (1, "2026-08-14"): [
            {
                "id": 148,
                "slot": "08:00 PM - 09:00 PM",
                "cost": 450,
                "is_booked": False,
                "is_busy": False,
                "is_reserved": False,
            },
            {
                "id": 147,
                "slot": "07:00 PM - 08:00 PM",
                "cost": 450,
                "is_booked": True,
                "is_busy": False,
                "is_reserved": False,
            },
        ]
    }

    grid = build_grid(courts=courts, dates=dates, slots_by_court_date=slots)

    assert grid["dates"] == ["2026-08-14", "2026-08-15"]
    assert grid["hours"] == ["07:00 PM - 08:00 PM", "08:00 PM - 09:00 PM"]
    friday = grid["courts"][0]["days"]["2026-08-14"]
    assert [cell["status"] for cell in friday] == ["booked", "free"]
    assert friday[0]["slot"] == "07:00 PM - 08:00 PM"
    saturday = grid["courts"][0]["days"]["2026-08-15"]
    assert saturday == [{"slot": None, "status": "closed", "cost": None, "id": None}]
