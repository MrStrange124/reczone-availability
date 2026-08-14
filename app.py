"""Vercel entrypoint.

Vercel's Python runtime resolves the function handler by looking for a top-level
`app` in one of a fixed set of filenames at the project root (`app.py`, `index.py`,
`main.py`, ...). The application itself lives in `reczone.server`; this module only
re-exports it so the deployed entrypoint and `python -m reczone` run the same code.
"""

from reczone.server import app

__all__ = ["app"]
