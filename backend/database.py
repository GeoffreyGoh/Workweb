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
# Defensive strip: a value pasted into a dashboard text box can carry a
# trailing newline, stray space, or surrounding quotes that are invisible
# in the UI but change the actual bytes sent to the driver - a stray
# character tacked onto the end of the password would make MySQL report
# "Access denied" even though the password looks identical on screen.
DATABASE_URL = DATABASE_URL.strip().strip("'\"")
IS_SQLITE = DATABASE_URL.startswith("sqlite")
IS_MYSQL = DATABASE_URL.startswith("mysql")

connect_args = {}
if IS_SQLITE:
    connect_args = {"check_same_thread": False}
elif IS_MYSQL:
    # Managed MySQL hosts (Aiven, PlanetScale, etc.) often publish a
    # connection string with an SSL query parameter in a spelling PyMySQL
    # (our driver, see requirements.txt) does not recognise - MySQL's own
    # URI convention is the hyphenated `ssl-mode` (seen from Aiven in
    # practice), while MySQL Connector/Python code elsewhere online uses
    # `ssl_mode`, and some providers just send `ssl=true`. SQLAlchemy
    # forwards any unrecognised query param straight to pymysql.connect(),
    # which raises `TypeError: unexpected keyword argument '...'` instead of
    # a connection error - so strip every spelling we've hit (a no-op if
    # none are present) and ask PyMySQL for TLS the way it actually
    # understands: a (possibly empty) `ssl` dict in connect_args enables an
    # encrypted connection without needing a bundled CA file, which matches
    # the "just require TLS" intent behind all of these spellings.
    SSL_PARAM_NAMES = ("ssl-mode", "ssl_mode", "ssl")
    url = make_url(DATABASE_URL)
    if any(name in url.query for name in SSL_PARAM_NAMES):
        query = {k: v for k, v in url.query.items() if k not in SSL_PARAM_NAMES}
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
