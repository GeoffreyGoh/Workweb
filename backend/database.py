"""Database connection.

Local dev defaults to SQLite so there's nothing to install. Production sets
DATABASE_URL to the managed database, e.g.

    DATABASE_URL=mysql+pymysql://user:***@host:3306/q2o?charset=utf8mb4

Same code either way.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
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
IS_MYSQL = DATABASE_URL.startswith("mysql")

connect_args = {}
if IS_SQLITE:
    connect_args = {"check_same_thread": False}
elif IS_MYSQL:
    # Managed MySQL hosts (Aiven, PlanetScale, etc.) often publish a
    # connection string with an `ssl_mode=REQUIRED` query parameter - that is
    # the MySQL Connector/Python spelling. PyMySQL (our driver, see
    # requirements.txt) has no such keyword and forwards every unrecognised
    # URL query param straight to pymysql.connect(), which raises
    # `TypeError: unexpected keyword argument 'ssl_mode'` instead of a
    # connection error. Strip it from the URL - harmless if absent - and ask
    # PyMySQL for TLS the way it actually understands: a (possibly empty)
    # `ssl` dict in connect_args enables an encrypted connection without
    # requiring a bundled CA file, which matches the "just require TLS"
    # intent of ssl_mode=REQUIRED for a well-known provider CA.
    url = make_url(DATABASE_URL)
    if "ssl_mode" in url.query:
        query = dict(url.query)
        query.pop("ssl_mode", None)
        url = url.set(query=query)
        DATABASE_URL = str(url)
    connect_args = {"ssl": {}}

# A serverless function gets its own process per instance, so a normal pool
# would multiply: 20 warm instances x 5 pooled connections exhausts the
# connection limit of a small managed MySQL. Open and close per request there.
POOL = {"poolclass": NullPool} if IS_SERVERLESS else {"pool_pre_ping": True}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
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
