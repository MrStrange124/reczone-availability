"""Read-only RecZone admin API client. Never locks or books slots."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class Transport(Protocol):
    async def get(self, path: str, params: dict | None = None) -> dict[str, Any]: ...


class ReczoneClient:
    def __init__(
        self,
        transport: Transport,
        identifier: str | None = None,
        locale: str = "en",
    ):
        self.transport = transport
        self.identifier = identifier or str(uuid.uuid4())
        self.locale = locale

    async def _data(self, path: str, params: dict | None = None) -> Any:
        query = {"locale": self.locale}
        if params:
            query.update(params)
        payload = await self.transport.get(path, query)
        return payload.get("data") or []

    async def complexes(self) -> list[dict[str, Any]]:
        return await self._data("/api/v1/bookings/membership-booking/reczones")

    async def facilities(self, reczone_id: int) -> list[dict[str, Any]]:
        return await self._data(
            f"/api/v1/general-slot-bookings/reczones/{reczone_id}/facilities"
        )

    async def courts(self, reczone_id: int, facility_id: int) -> list[dict[str, Any]]:
        return await self._data(
            f"/api/v1/general-slot-bookings/reczones/{reczone_id}/facilities/{facility_id}/facility-subtypes"
        )

    async def dates(
        self, reczone_id: int, facility_id: int, court_id: int
    ) -> list[dict[str, Any]]:
        return await self._data(
            f"/api/v1/general-slot-bookings/reczones/{reczone_id}/facilities/{facility_id}/facility-subtypes/{court_id}/dates"
        )

    async def timeslots(
        self, reczone_id: int, facility_id: int, court_id: int, date: str
    ) -> list[dict[str, Any]]:
        return await self._data(
            f"/api/v1/general-slot-bookings/reczones/{reczone_id}/facilities/{facility_id}/facility-subtypes/{court_id}/timeslots",
            {
                "identifier": self.identifier,
                "date_of_booking": date,
            },
        )
