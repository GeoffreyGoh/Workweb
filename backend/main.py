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
