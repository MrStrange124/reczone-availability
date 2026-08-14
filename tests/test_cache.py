import pytest

from reczone.cache import CachingTransport, ResponseCache


class CountingTransport:
    def __init__(self, payload=None, fail_times: int = 0):
        self.payload = payload or {"code": 200, "data": [{"id": 1}]}
        self.calls: list[tuple[str, dict]] = []
        self.fail_times = fail_times

    async def get(self, path: str, params: dict | None = None):
        self.calls.append((path, params or {}))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("upstream is unhappy")
        return self.payload


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def build(ttl=120.0, **kwargs):
    clock = FakeClock()
    inner = CountingTransport(**kwargs)
    cache = ResponseCache(ttl=ttl, clock=clock)
    return CachingTransport(inner, cache), inner, clock


async def test_second_read_inside_the_window_never_reaches_upstream():
    transport, inner, _ = build()

    first = await transport.get("/timeslots", {"date_of_booking": "2026-08-18"})
    second = await transport.get("/timeslots", {"date_of_booking": "2026-08-18"})

    assert first == second
    assert len(inner.calls) == 1


async def test_read_after_the_window_refetches():
    transport, inner, clock = build(ttl=120.0)

    await transport.get("/timeslots")
    clock.advance(119.0)
    await transport.get("/timeslots")
    assert len(inner.calls) == 1

    clock.advance(2.0)
    await transport.get("/timeslots")
    assert len(inner.calls) == 2


async def test_params_are_part_of_the_key():
    transport, inner, _ = build()

    await transport.get("/timeslots", {"date_of_booking": "2026-08-18"})
    await transport.get("/timeslots", {"date_of_booking": "2026-08-19"})

    assert len(inner.calls) == 2


async def test_key_ignores_param_ordering():
    transport, inner, _ = build()

    await transport.get("/timeslots", {"a": "1", "b": "2"})
    await transport.get("/timeslots", {"b": "2", "a": "1"})

    assert len(inner.calls) == 1


async def test_failures_are_not_cached():
    """A cached failure would outlive the blip that caused it."""
    transport, inner, _ = build(fail_times=1)

    with pytest.raises(RuntimeError):
        await transport.get("/timeslots")

    payload = await transport.get("/timeslots")
    assert payload["data"][0]["id"] == 1
    assert len(inner.calls) == 2


async def test_callers_cannot_mutate_what_the_next_caller_reads():
    transport, inner, _ = build()

    first = await transport.get("/timeslots")
    first["data"][0]["id"] = 999
    first["data"].append({"id": "junk"})

    second = await transport.get("/timeslots")
    assert second["data"] == [{"id": 1}]
    assert len(inner.calls) == 1


async def test_upstream_payload_is_not_captured_by_reference():
    """The transport hands back its own parsed dict; if the cache stored that
    object, a caller mutating it would rewrite the cached entry."""
    clock = FakeClock()
    payload = {"code": 200, "data": [{"id": 1}]}
    inner = CountingTransport(payload=payload)
    transport = CachingTransport(inner, ResponseCache(clock=clock))

    await transport.get("/timeslots")
    payload["data"][0]["id"] = 42

    assert (await transport.get("/timeslots"))["data"][0]["id"] == 1


async def test_expired_entries_are_reclaimed():
    clock = FakeClock()
    cache = ResponseCache(ttl=120.0, clock=clock, max_entries=8)
    transport = CachingTransport(CountingTransport(), cache)

    for index in range(8):
        await transport.get(f"/timeslots/{index}")
    assert len(cache) == 8

    clock.advance(121.0)
    await transport.get("/timeslots/fresh")
    assert len(cache) == 1


async def test_cache_stays_within_its_ceiling():
    clock = FakeClock()
    cache = ResponseCache(ttl=120.0, clock=clock, max_entries=4)
    transport = CachingTransport(CountingTransport(), cache)

    for index in range(12):
        clock.advance(0.1)
        await transport.get(f"/timeslots/{index}")

    assert len(cache) <= 4


def test_eviction_drops_the_oldest_write_even_after_a_rewrite():
    """Eviction reads insertion order as expiry order, so a rewritten key has to
    move to the back or it gets dropped while something staler survives."""
    clock = FakeClock()
    cache = ResponseCache(ttl=120.0, clock=clock, max_entries=3)

    cache.set(("a", ()), {"v": 1})
    cache.set(("b", ()), {"v": 2})
    cache.set(("a", ()), {"v": 3})  # rewritten, so now the newest
    cache.set(("c", ()), {"v": 4})
    cache.set(("d", ()), {"v": 5})  # at the ceiling: something must go

    assert cache.get(("b", ())) is None, "b was the oldest survivor"
    assert cache.get(("a", ())) == {"v": 3}


async def test_clear_empties_the_store():
    transport, inner, _ = build()
    await transport.get("/timeslots")
    transport.cache.clear()
    await transport.get("/timeslots")
    assert len(inner.calls) == 2
