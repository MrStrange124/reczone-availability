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
