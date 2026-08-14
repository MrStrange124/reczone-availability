"""Slot status and court × date grid assembly for RecZone availability."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence


def classify_slot(slot: Mapping[str, Any]) -> str:
    if slot.get("is_booked"):
        return "booked"
    if slot.get("is_busy"):
        return "busy"
    if slot.get("is_reserved"):
        return "reserved"
    return "free"


def slot_sort_key(label: str) -> int:
    start = label.split(" - ", 1)[0].strip()
    parsed = datetime.strptime(start, "%I:%M %p")
    return parsed.hour * 60 + parsed.minute


def filter_dates(
    months: Sequence[Mapping[str, Any]],
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for month in months:
        for day in month.get("dates") or []:
            date = day.get("date")
            if date and start <= date <= end:
                selected.append(dict(day))
    selected.sort(key=lambda day: day["date"])
    return selected


def build_grid(
    *,
    courts: Sequence[Mapping[str, Any]],
    dates: Sequence[Mapping[str, Any]],
    slots_by_court_date: Mapping[tuple[int, str], Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    hours: set[str] = set()
    rows: list[dict[str, Any]] = []

    for court in courts:
        court_id = int(court["id"])
        by_date: dict[str, list[dict[str, Any]]] = {}
        for day in dates:
            date = day["date"]
            raw_slots = slots_by_court_date.get((court_id, date), [])
            cells = []
            if day.get("isClosed"):
                cells = [{"slot": None, "status": "closed", "cost": None, "id": None}]
            else:
                for raw in raw_slots:
                    label = raw["slot"]
                    hours.add(label)
                    cells.append(
                        {
                            "id": raw.get("id"),
                            "slot": label,
                            "cost": raw.get("cost"),
                            "status": classify_slot(raw),
                        }
                    )
                cells.sort(key=lambda cell: slot_sort_key(cell["slot"]))
            by_date[date] = cells
        rows.append(
            {
                "id": court_id,
                "name": court.get("name"),
                "dimension": court.get("dimension"),
                "days": by_date,
            }
        )

    return {
        "dates": [day["date"] for day in dates],
        "date_meta": [
            {
                "date": day["date"],
                "day": day.get("day"),
                "dayOfWeek": day.get("dayOfWeek"),
                "isClosed": bool(day.get("isClosed")),
            }
            for day in dates
        ],
        "hours": sorted(hours, key=slot_sort_key),
        "courts": rows,
    }
