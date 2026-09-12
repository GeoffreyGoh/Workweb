"""Vercel entrypoint.

Vercel's Python runtime looks for `app.py` (or index/server/main) at the
project root and serves the top-level `app` it finds there. The application
itself lives in backend/, so put that on the import path first.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from main import app  # noqa: E402  - the path above has to be set first

__all__ = ["app"]
