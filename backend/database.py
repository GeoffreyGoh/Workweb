"""Database connection.

Local dev defaults to SQLite so there's nothing to install. Production sets
DATABASE_URL to the managed database, e.g.

    DATABASE_URL=mysql+pymysql://user:pass@host:3306/q2o?charset=utf8mb4

Same code either way.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# Serverless hosts (Vercel, Lambda) have a read-only filesystem apart from
# /tmp, so a SQLite fallback has to live there. It is per-instance and wiped
# between cold starts - fine for a smoke test, useless as real storage, which
# is why production must set DATABASE_URL to a managed database.
IS_SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

DATABASE_URL = os.getenv("DATABASE_URL") or (
    "sqlite:////tmp/q2o.db" if IS_SERVERLESS else "sqlite:///./q2o.db"
)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# A serverless function gets its own process per instance, so a normal pool
# would multiply: 20 warm instances x 5 pooled connections exhausts the
# connection limit of a small managed MySQL. Open and close per request there.
POOL = {"poolclass": NullPool} if IS_SERVERLESS else {"pool_pre_ping": True}

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    future=True,
    **POOL,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
