from reczone.slots import classify_slot


def test_booked_slot_wins_over_other_flags():
    assert (
        classify_slot(
            {"id": 1, "slot": "07:00 PM - 08:00 PM", "is_booked": True, "is_busy": True, "is_reserved": True}
        )
        == "booked"
    )


def test_busy_slot_is_held_when_not_booked():
    assert (
        classify_slot(
            {"id": 2, "slot": "06:00 PM - 07:00 PM", "is_booked": False, "is_busy": True, "is_reserved": False}
        )
        == "busy"
    )


def test_reserved_slot_is_not_free_for_general_booking():
    assert (
        classify_slot(
            {"id": 3, "slot": "05:00 AM - 06:00 AM", "is_booked": False, "is_busy": False, "is_reserved": True}
        )
        == "reserved"
    )


def test_open_slot_is_free():
    assert (
        classify_slot(
            {"id": 4, "slot": "08:00 AM - 09:00 AM", "is_booked": False, "is_busy": False, "is_reserved": False}
        )
        == "free"
    )
