"""Vercel serverless function entry point for FastAPI.

This file is loaded by Vercel's Python runtime and provides the ASGI app
that handles all requests. Vercel injects this into a gunicorn process.
"""

import sys
from pathlib import Path

# Add backend directory to Python path so imports work
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

# Import the FastAPI app from main.py
from main import app

# Vercel expects a callable ASGI app named 'app'
__all__ = ["app"]
