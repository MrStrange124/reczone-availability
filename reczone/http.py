"""Live HTTP transport for the RecZone admin API."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

import httpx

RECZONE_ADMIN = "https://reczone-admin.mcgm.gov.in"
USER_AGENT = "RecZoneAvailabilityViewer/1.0 (read-only; local)"

Sleep = Callable[[float], Awaitable[None]]


class HttpxTransport:
    def __init__(
        self,
        http: httpx.AsyncClient,
        retries: int = 4,
        backoff: float = 0.6,
        sleeper: Sleep | None = None,
    ):
        self.http = http
        self.retries = retries
        self.backoff = backoff
        self.sleeper = sleeper or asyncio.sleep

    async def get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        last_error: httpx.HTTPStatusError | None = None
        for attempt in range(self.retries + 1):
            response = await self.http.get(path, params=params)
            if response.status_code == 404:
                return {"code": 404, "data": []}
            if response.status_code == 429 and attempt < self.retries:
                await self.sleeper(_retry_delay(response, self.backoff, attempt))
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                break
            return response.json()
        assert last_error is not None
        raise last_error


def _retry_delay(response: httpx.Response, backoff: float, attempt: int) -> float:
    raw = response.headers.get("Retry-After")
    if raw is not None:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return backoff * (2**attempt)


def build_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=RECZONE_ADMIN,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    )
