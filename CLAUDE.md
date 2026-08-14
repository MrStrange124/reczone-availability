# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A read-only availability viewer for [BMC RecZone](https://reczone.mcgm.gov.in/sports-complex/book-your-sport?complex=2&type=1),
Mumbai's municipal sports booking system. It proxies RecZone's admin API and renders
a week of court availability. **It never signs in, holds, or books a slot** — treat that
as an invariant, not a current limitation.

## Commands

```bash
python3 -m reczone                                    # dev server, 127.0.0.1:8765, reload on
python3 -m uvicorn reczone.server:app --reload --port 8765   # equivalent, explicit

python3 -m pytest                                     # full suite
python3 -m pytest tests/test_cache.py                 # one file
python3 -m pytest tests/test_cache.py::test_failures_are_not_cached   # one test
python3 -m pytest -q -k cache                         # by name

npx vercel        # preview deploy
npx vercel --prod
```

Dependencies are in `requirements.txt`. PyPI is optional here — conda works:
`conda install -c conda-forge fastapi uvicorn httpx pytest pytest-asyncio`.
`.python-version` pins 3.13 to match the Vercel runtime.

## Architecture

### The transport chain

`ReczoneClient` depends on a `Transport` Protocol (`reczone/client.py`), never on httpx
directly. `server.get_client` composes the stack:

```
ReczoneClient → CachingTransport → HttpxTransport → RecZone admin API
```

Cross-cutting concerns belong in a new `Transport` wrapper, not in the endpoints or the
client. That is how caching was added without touching a single route, and how retry /
429 handling already lives in `HttpxTransport`.

### The fan-out is the whole cost model

`availability.fetch_grid` issues `courts` + `dates` + (courts × dates) timeslot calls —
about **51 requests taking ~11s** for a 7-day badminton week. RecZone allows **60
requests/minute per caller**. Concurrency is capped at 3 by a semaphore. Almost every
non-obvious decision in this repo traces back to that budget; check it before adding any
new upstream read.

### Two caches, one 60-second window

| Layer | Where | Knob |
|---|---|---|
| Shared/CDN | `Cache-Control` response headers | `GRID_CACHE`, `REFERENCE_CACHE` |
| Origin | in-process TTL store, `reczone/cache.py` | `CACHE_TTL` (60.0), `RESPONSE_CACHE` |

They are aligned on purpose so the origin stops trusting a grid at the same moment the
CDN does — if they diverge, a CDN revalidation can be answered from a staler origin copy
and a booking stays invisible for the difference. **Change both together.**

Only successful reads are cached; a cached 429 would outlive the blip that caused it.
Payloads are deep-copied in and out, because the transport hands back the dict it just
parsed and callers keep reading from it.

### Serverless constraints that look like over-engineering

These exist because Vercel's Python runtime is not a long-lived process. Do not
"simplify" them without reading `reczone/server.py`'s comments and `tests/test_server.py`:

- **`_http()` keys the httpx client on the running event loop, not the process.** A
  connection pool is bound to the loop that opened it; reusing one across loops fails
  with `Event loop is closed`. `get_client` is `async` for the same reason — sync
  dependencies run in a worker thread with no loop to key on.
- **ASGI lifespan may never run**, so `_http` builds the client on demand rather than
  trusting `app.state`.
- **`ResponseCache` is a plain dict**, deliberately nothing loop-bound, so it survives
  loop rotation on a warm instance.
- **`VIEWER_IDENTIFIER` is minted once per process**, not per request. It travels as a
  `timeslots` query param, so a fresh uuid each time would give every read in the fan-out
  its own cache key and the cache would never hit. Nothing is locked or booked under it.
- **`app.py` only re-exports `reczone.server:app`** because Vercel resolves its handler
  from a top-level `app` in a root-level file. `vercel.json` keys function config on it.

### Slot status vocabulary

Upstream distinguishes `booked` / `busy` / `reserved` / free, plus whole-day `isClosed`.
`slots.classify_slot` maps those; `slots.build_grid` assembles the court-major payload.

The UI deliberately collapses all of them to **open vs taken** — the three "taken"
variants differ only in RecZone's internal bookkeeping, not in anything a player can act
on. The breakdown survives in each tape cell's tooltip. Don't reintroduce a five-colour
legend without a reason.

### Frontend

`static/` is dependency-free ES modules and hand-written CSS; there is no build step.

The server returns a **court-major** grid (`courts[].days[date][]`). `app.js`'s
`analyse(grid)` pivots it into **day × hour** cells carrying an open-count. That pivot is
the core UI decision: all courts at a venue are interchangeable (identical dimensions),
so collapsing them into a count per hour is what lets a full week fit a phone screen with
no horizontal scrolling. Two views render from that model — the tape (`renderTape`) and
the openings call sheet (`renderWindows`).

Note `todayStamp()` uses local date parts, not `toISOString()`: RecZone dates are Mumbai
dates, and before 05:30 IST the UTC date is still yesterday.

## Testing conventions

- `pytest.ini` sets `asyncio_mode = auto` — async tests need no decorator.
- `tests/conftest.py` has an autouse fixture clearing `RESPONSE_CACHE`, which is
  process-wide by design. Tests must not inherit each other's cached entries.
- Fake upstreams: `FakeTransport` (hand-rolled, `test_client.py`) or `httpx.MockTransport`
  (`test_http.py`, `test_server.py`). Endpoint tests use
  `app.dependency_overrides[get_client]` and clear it in a `finally`.
- Tests reach the real httpx client through `client.transport.inner.http` — one level
  deeper than it looks, because of the caching wrapper.
- Several tests encode *why* a shape exists (loop rotation, missing lifespan, cache
  expiry) in their docstrings. If one starts failing, read the docstring before changing
  the assertion.

## Working against the live API

Iterating on the UI against the real server burns the 60/min budget fast. Prefer saving
API responses to fixtures and serving them from a throwaway static server.

`/api/grid` input handling, in order: FastAPI parses `start`/`end` as `datetime.date`
(422 on junk — they were once bare strings, where `"yesterday"` compared lexically and
produced a confident but wrong "End date is before start date"); then `end < start` is a
400; then `court_ids` is split and `int()`ed behind a 400. Upstream 429s surface as a 429
with a readable `detail` rather than a 500.
