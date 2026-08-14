"""Fan-out RecZone reads into a court × date availability grid."""

from __future__ import annotations

import asyncio
from typing import Any, Sequence

from reczone.slots import build_grid, filter_dates


async def fetch_grid(
    client,
    *,
    reczone_id: int,
    facility_id: int,
    court_ids: Sequence[int] | None,
    start: str,
    end: str,
    concurrency: int = 3,
) -> dict[str, Any]:
    courts = await client.courts(reczone_id, facility_id)
    if court_ids:
        wanted = {int(court_id) for court_id in court_ids}
        courts = [court for court in courts if int(court["id"]) in wanted]
    if not courts:
        return build_grid(courts=[], dates=[], slots_by_court_date={})

    months = await client.dates(reczone_id, facility_id, int(courts[0]["id"]))
    dates = filter_dates(months, start, end)

    semaphore = asyncio.Semaphore(concurrency)
    slots_by_court_date: dict[tuple[int, str], list[dict[str, Any]]] = {}

    async def load(court_id: int, date: str) -> None:
        async with semaphore:
            slots_by_court_date[(court_id, date)] = await client.timeslots(
                reczone_id, facility_id, court_id, date
            )

    tasks = [
        load(int(court["id"]), day["date"])
        for court in courts
        for day in dates
        if not day.get("isClosed")
    ]
    if tasks:
        await asyncio.gather(*tasks)

    return build_grid(courts=courts, dates=dates, slots_by_court_date=slots_by_court_date)
