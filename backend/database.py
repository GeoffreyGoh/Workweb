"""Database connection.

Local dev defaults to SQLite so there's nothing to install. Production sets
DATABASE_URL to the managed MySQL instance, e.g.

    DATABASE_URL=mysql+pymysql://user:pass@host:3306/q2o?charset=utf8mb4

Same code either way.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# backend/database.py — replace from 'load_dotenv()' block down to engine creation

load_dotenv()

# Resolve database URL. Prefer an explicit DATABASE_URL environment variable.
# For serverless platforms (Vercel) the repository root is read-only; use /tmp.
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Detect Vercel or similar serverless envs and fall back to /tmp
    if os.getenv("VERCEL") or os.getenv("VERCEL_ENV") or os.getenv("NOW_REGION"):
        DATABASE_URL = "sqlite:////tmp/q2o.db"
    else:
        DATABASE_URL = "sqlite:///./q2o.db"

IS_SQLITE = DATABASE_URL.startswith("sqlite")

# Create engine; wrap in try/except so import-time errors are printed to logs.
try:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False} if IS_SQLITE else {},
        pool_pre_ping=True,
        future=True,
    )
except Exception:
    # Print the exception and some env context to stderr so Vercel's logs include it.
    import traceback, sys

    traceback.print_exc()
    print("DATABASE_URL:", DATABASE_URL, file=sys.stderr)
    # Re-raise so the platform still fails the deployment (we want the stack trace).
    raise

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()
