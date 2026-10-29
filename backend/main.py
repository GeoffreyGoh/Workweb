"""Q2O API.

Run from the backend/ directory:

    uvicorn main:app --reload

The frontend is served from the same origin at http://localhost:8000/app/login.html
so there is nothing else to start.
"""

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import auth
import models  # noqa: F401  - registers the mapped classes
import schemas
from database import get_db
from routers import (
    companies,
    customers,
    delivery_notes,
    documents,
    products,
    purchase_orders,
    quotations,
    receipts,
    reports,
    sales_orders,
    suppliers,
    users,
)

app = FastAPI(title="Q2O API", version="0.4.0")

# Only relevant if the frontend is ever served from a different host.
origins = os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------- auth
@app.post("/auth/login", response_model=schemas.Token, tags=["auth"])
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = auth.authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return schemas.Token(access_token=auth.create_access_token(user.username, user.role))


@app.get("/auth/me", response_model=schemas.UserOut, tags=["auth"])
def read_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/health/db", tags=["meta"])
def health_db(db: Session = Depends(get_db)):
    """Round-trip the actual database connection and report what happened.

    Deliberately temporary - added to shortcut the dashboard-log-screenshot
    loop while diagnosing a production DB connection issue; safe to remove
    once things are stable, since it leaks no secrets (no password, no
    connection string) but does confirm whether the DB is reachable at all.
    """
    from sqlalchemy import text

    import database

    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "message": "database connection succeeded"}
    except Exception as exc:  # noqa: BLE001 - intentionally broad, this is a diagnostic
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "is_mysql": database.IS_MYSQL,
            "is_sqlite": database.IS_SQLITE,
        }


@app.get("/health/db-variants", tags=["meta"])
def health_db_variants():
    """Try several connection strategies against the same DATABASE_URL.

    The standing connection in `database.engine` keeps failing with MySQL
    error 1045 (Access denied) from Vercel specifically, even though the
    identical credentials work from a local machine. That symptom is the
    classic signature of `caching_sha2_password` (MySQL 8's default auth
    plugin) needing a fully negotiated TLS channel or the server's RSA
    public key to transmit the password securely - if the environment's
    OpenSSL/cryptography build can't complete that handshake the same way
    a desktop Python can, MySQL reports it as a wrong password rather than
    a TLS failure, which is exactly what we have been seeing.

    This tries three PyMySQL connect_args variants directly (bypassing the
    pooled engine) and reports which ones succeed, so the real fix can be
    picked in one round trip instead of guessing through more redeploys.
    Temporary; safe to remove once the connection is stable.
    """
    import pymysql
    from sqlalchemy.engine import make_url

    import database

    if not database.IS_MYSQL:
        return {"status": "skipped", "reason": "DATABASE_URL is not a MySQL URL"}

    url = make_url(database.DATABASE_URL)
    base_kwargs = dict(
        host=url.host, port=url.port or 3306, user=url.username,
        password=url.password, database=url.database,
    )

    variants = {
        # 1. No SSL at all - works only if Aiven accepts a plaintext fallback.
        "no_ssl": {},
        # 2. Empty ssl dict - what database.py currently sends.
        "ssl_empty_dict": {"ssl": {}},
        # 3. Explicitly fetch the server's RSA key for caching_sha2_password
        #    over a non-TLS channel - PyMySQL's documented way to let the
        #    auth plugin complete without a full SSL context.
        "ssl_none_get_public_key": {"ssl": None, "get_server_public_key": True},
    }

    results = {}
    for name, extra_kwargs in variants.items():
        try:
            conn = pymysql.connect(**base_kwargs, **extra_kwargs, connect_timeout=5)
            conn.close()
            results[name] = {"status": "ok"}
        except Exception as exc:  # noqa: BLE001 - intentionally broad, this is a diagnostic
            results[name] = {"status": "error", "error_type": type(exc).__name__,
                              "error_message": str(exc)}

    return {"variants": results}


app.include_router(companies.router)
app.include_router(products.router)
app.include_router(customers.router)
app.include_router(suppliers.router)
app.include_router(users.router)
app.include_router(quotations.router)
app.include_router(sales_orders.router)
app.include_router(purchase_orders.router)
app.include_router(delivery_notes.router)
app.include_router(receipts.router)
app.include_router(reports.router)
app.include_router(documents.router)


# ------------------------------------------------------------------ frontend
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse(url="/app/login.html")
