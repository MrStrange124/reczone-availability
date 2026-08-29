# RecZone court sheet

Read-only availability viewer for [BMC RecZone](https://reczone.mcgm.gov.in/sports-complex/book-your-sport?complex=2&type=1). It answers one question — when can I actually play this week? — and does not log in, lock, or book.

Live at **[reczone-availability.vercel.app](https://reczone-availability.vercel.app)**.

The page reads as two views of the same data:

- **The week.** A day × hour tape, one bar per hour, its height the number of courts open then. Courts collapse into a count because they are interchangeable (all seven badminton courts are the same 968 sq ft), and that collapse is what lets a full week fit on a phone with no sideways scrolling.
- **Open windows.** Every opening set at headline scale, grouped by day, with the courts and the hourly rate. Openings are scarce enough to deserve the space: a typical badminton week is ~9% free, so the list runs to a dozen or so entries.

The five upstream statuses collapse to two on screen. `booked`, `busy`, and `reserved` are all "you cannot have it" and differ only in RecZone's internal bookkeeping; the tape encodes open versus taken, and the per-hour breakdown stays available in each cell's tooltip.

## Run

From this directory:

```bash
python3 -m reczone
```

or:

```bash
python3 -m uvicorn reczone.server:app --reload --port 8765
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). Defaults to Shahaji Raje Bhosle Kreeda Sankul, Andheri / badminton / all wooden courts / the dates RecZone is currently selling (about a week).

PyPI is optional here; FastAPI can be installed with conda:

```bash
conda install -c conda-forge fastapi uvicorn httpx pytest pytest-asyncio
```

## Tests

```bash
python3 -m pytest
```

## Deploy (Vercel)

Production is <https://reczone-availability.vercel.app>, served from `bom1`.

```bash
scripts/deploy.sh          # preview
scripts/deploy.sh --prod   # production
```

Plain `npx vercel` from this directory comes back **BLOCKED** before it builds. The
CLI notices the GitHub remote, stamps the deployment `githubDeployment: 1`, and
Vercel then resolves the commit author through GitHub — and the GitHub identity
`MrStrange124` is not linked to the Vercel account, so it is refused. The address on
the commit is a red herring: forcing `-m githubCommitAuthorEmail=<account email>`
rewrites the metadata and still blocks, because the *identity* is what gets checked,
not the string.

`scripts/deploy.sh` stages the tracked files into a temp directory with no `.git`,
which leaves the CLI nothing to attach, and the deploy goes straight through.

The one-time real fix is to link the GitHub login under Vercel account settings.
After that `npx vercel --prod` works from here directly and the script can go.

`app.py` re-exports `reczone.server:app` because Vercel's Python runtime resolves its
handler from a top-level `app` in a root-level file. `vercel.json` keys the function
config on `app.py`; `.python-version` pins 3.13 to match local dev.

Three things about this app are shaped by the host rather than by preference:

- **Cache headers are load-bearing.** RecZone allows 60 requests/minute per caller and
  one full grid render fans out to ~51 calls in ~9s, so a single uncached page load eats
  most of the budget and two concurrent viewers would 429 each other. `s-maxage` on the
  API responses means the CDN pays that cost once per window no matter how many people
  are watching. Lower it and the deployment rate-limits itself.
- **The origin keeps its own one-minute memory** (`reczone.cache`, `CACHE_TTL`). The
  headers above only help where a shared cache sits in front of us; this covers the
  requests the CDN chose not to answer. It matches `GRID_CACHE`'s `s-maxage` on
  purpose, so the origin stops trusting a grid at the same moment the CDN does. It sits under `ReczoneClient` as a `Transport`,
  so every endpoint benefits without knowing about it, and a repeat grid render inside
  the window costs nothing upstream — measured at 10.9s cold against 0.013s warm, for a
  byte-identical body. Only successful reads are stored: caching a 429 would outlive the
  blip that caused it. Two details make it work — the store is a plain dict rather than
  anything bound to an event loop (same hazard as the HTTP client below), and
  `VIEWER_IDENTIFIER` is minted once per process instead of per request, because it
  rides along as a timeslots query param and a fresh uuid each time would give every
  read in the fan-out its own cache key.
- **The HTTP client is cached per event loop, not per process** (`reczone.server._http`).
  Serverless runtimes need not run ASGI lifespan, and a client's connection pool is
  bound to the loop that opened it, so a process-wide client can outlive its loop and
  fail with `Event loop is closed`. `get_client` is `async` for the same reason: sync
  dependencies run in a worker thread with no loop to key the cache on.
