# RecZone court sheet

Local, read-only availability viewer for [BMC RecZone](https://reczone.mcgm.gov.in/sports-complex/book-your-sport?complex=2&type=1). It shows a court × date grid for general slots. It does not log in, lock, or book.

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

```bash
npx vercel        # preview
npx vercel --prod # production
```

`app.py` re-exports `reczone.server:app` because Vercel's Python runtime resolves its
handler from a top-level `app` in a root-level file. `vercel.json` keys the function
config on `app.py`; `.python-version` pins 3.13 to match local dev.

Two things about this app are shaped by the host rather than by preference:

- **Cache headers are load-bearing.** RecZone allows 60 requests/minute per caller and
  one full grid render fans out to ~51 calls in ~9s, so a single uncached page load eats
  most of the budget and two concurrent viewers would 429 each other. `s-maxage` on the
  API responses means the CDN pays that cost once per window no matter how many people
  are watching. Lower it and the deployment rate-limits itself.
- **The HTTP client is cached per event loop, not per process** (`reczone.server._http`).
  Serverless runtimes need not run ASGI lifespan, and a client's connection pool is
  bound to the loop that opened it, so a process-wide client can outlive its loop and
  fail with `Event loop is closed`. `get_client` is `async` for the same reason: sync
  dependencies run in a worker thread with no loop to key the cache on.
