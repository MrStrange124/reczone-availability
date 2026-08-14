"""Short-lived server-side cache for RecZone reads.

RecZone allows 60 requests/minute per caller and one grid render fans out to
roughly courts x dates requests, so the same handful of upstream reads is worth
holding onto briefly. This sits under `ReczoneClient` as a `Transport`, which
means every endpoint benefits without any of them knowing about it.

Two shapes here are deliberate:

- **The store is a plain dict, not anything bound to an event loop.** A warm
  serverless instance may serve successive invocations on different loops (see
  `reczone.server._http` for the same hazard); unlike an httpx connection pool, a
  dict does not care which loop is running.
- **Payloads are copied in and out.** The transport hands back the dict it just
  parsed and callers keep reading from it, so storing that object by reference
  would let one caller's edit rewrite what the next caller sees.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any, Callable

DEFAULT_TTL = 60.0
DEFAULT_MAX_ENTRIES = 1024

Key = tuple[str, tuple[tuple[str, Any], ...]]


def cache_key(path: str, params: dict | None) -> Key:
    return path, tuple(sorted((params or {}).items()))


@dataclass(frozen=True)
class _Entry:
    payload: dict
    expires_at: float


class ResponseCache:
    """A process-wide, TTL'd store of upstream payloads."""

    def __init__(
        self,
        ttl: float = DEFAULT_TTL,
        clock: Callable[[], float] = time.monotonic,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ):
        self.ttl = ttl
        self.clock = clock
        self.max_entries = max_entries
        self._entries: dict[Key, _Entry] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: Key) -> dict | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= self.clock():
            del self._entries[key]
            return None
        return copy.deepcopy(entry.payload)

    def set(self, key: Key, payload: dict) -> None:
        now = self.clock()
        if len(self._entries) >= self.max_entries:
            self._reclaim(now)
        # Re-inserting rather than overwriting keeps insertion order equal to write
        # order, which under one fixed TTL is also expiry order. `_reclaim` relies
        # on that to find the oldest entry without scanning.
        self._entries.pop(key, None)
        self._entries[key] = _Entry(copy.deepcopy(payload), now + self.ttl)

    def clear(self) -> None:
        self._entries.clear()

    def _reclaim(self, now: float) -> None:
        for key in [k for k, e in self._entries.items() if e.expires_at <= now]:
            del self._entries[key]
        # Nothing has expired yet but the store is full: drop whatever is closest to
        # expiring, which by the invariant above is simply the oldest key.
        while len(self._entries) >= self.max_entries:
            del self._entries[next(iter(self._entries))]


class CachingTransport:
    """Wraps a `Transport`, serving repeat reads from `cache`.

    Only successful reads are stored. A cached failure would outlive the blip
    that caused it, and RecZone's 429s are exactly the transient kind.
    """

    def __init__(self, inner, cache: ResponseCache):
        self.inner = inner
        self.cache = cache

    async def get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        key = cache_key(path, params)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        payload = await self.inner.get(path, params)
        self.cache.set(key, payload)
        return payload
