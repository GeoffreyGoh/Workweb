"""Shared test fixtures.

Every test runs against a throwaway SQLite file with the tables recreated
between tests, so no test can see another one's rows and numbering always
starts from 001.
"""

import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# The app uses flat imports (`import models`), so backend/ must be importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth  # noqa: E402
import models  # noqa: E402
from database import Base, get_db  # noqa: E402
from main import app  # noqa: E402

# bcrypt is deliberately slow (~0.3s per hash), which the suite pays for on
# every fixture. Four rounds keeps the same algorithm and code path while
# taking the suite from ~30s to ~2s.
from passlib.context import CryptContext  # noqa: E402

auth.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=4)

# One in-memory database shared by every connection in the process.
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


def dec(value) -> Decimal:
    """API money values arrive as JSON strings; compare them as Decimals."""
    return Decimal(str(value))


@pytest.fixture()
def db():
    """A clean schema for each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------- companies
@pytest.fixture()
def companies(db):
    """Two entities sharing one catalogue, as in production."""
    rows = [
        models.Company(code="GB", name="PT Graha Blinds Nusantara",
                       address="Jl. Contoh No. 1", city="Jakarta",
                       phone="021-111", email="gb@example.co.id",
                       website="www.gb.co.id", npwp="01.111.111.1-111.000",
                       bank_name="BCA", bank_account="1234567890",
                       bank_holder="PT Graha Blinds Nusantara",
                       signatory="Sales Manager"),
        models.Company(code="MJ", name="PT Mitra Jendela Indah",
                       address="Jl. Serpong No. 2", city="Tangerang",
                       phone="021-222", email="mj@example.co.id",
                       website="www.mj.co.id", npwp="02.222.222.2-222.000",
                       bank_name="Mandiri", bank_account="9876543210",
                       bank_holder="PT Mitra Jendela Indah",
                       signatory="Direktur"),
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return {c.code: c for c in rows}


# ------------------------------------------------------------------- users
@pytest.fixture()
def users(db, companies):
    """One admin and two ordinary users, defaulted to the first company."""
    default = companies["GB"].id
    rows = [
        models.User(username="admin", full_name="Administrator",
                    password_hash=auth.hash_password("admin123"), role="admin",
                    default_company_id=default),
        models.User(username="budi", full_name="Budi Santoso",
                    password_hash=auth.hash_password("budi123"), role="user",
                    default_company_id=default),
        models.User(username="sari", full_name="Sari Dewi",
                    password_hash=auth.hash_password("sari123"), role="user",
                    default_company_id=default),
        models.User(username="gone", full_name="Left The Company",
                    password_hash=auth.hash_password("gone123"), role="user",
                    is_active=False),
    ]
    db.add_all(rows)
    db.commit()
    return {u.username: u.id for u in rows}


def _headers(client, username, password):
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def admin(client, users):
    return _headers(client, "admin", "admin123")


@pytest.fixture()
def budi(client, users):
    return _headers(client, "budi", "budi123")


@pytest.fixture()
def sari(client, users):
    return _headers(client, "sari", "sari123")


# ----------------------------------------------------------------- masters
@pytest.fixture()
def customer(db):
    row = models.Customer(
        code="CUST-001", name="PT Graha Interior", nik_npwp="01.234.567.8-901.000",
        address="Jl. Sudirman No. 45, Jakarta", phone="021-5551234",
        email="buy@graha.co.id", price_group="RETAIL", payment_terms="30 days",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def customer2(db):
    row = models.Customer(code="CUST-002", name="Hotel Santika", address="Medan")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def supplier(db):
    row = models.Supplier(
        code="SUP-001", name="PT Tekstil Nusantara",
        address="Pulogadung, Jakarta", payment_terms="30 days",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def products(db):
    """One product per pricing unit, with deliberately tight limits."""
    rows = {
        "sqm": models.Product(
            code="RB-SQM", name="Roller Blind", price_unit="per_sqm",
            unit_price=Decimal("400000"),
            min_width_cm=Decimal("40"), max_width_cm=Decimal("300"),
            min_height_cm=Decimal("40"), max_height_cm=Decimal("400"),
        ),
        "meter": models.Product(
            code="TRK-M", name="Curtain Track", price_unit="per_meter",
            unit_price=Decimal("100000"),
            min_width_cm=Decimal("60"), max_width_cm=Decimal("800"),
        ),
        "unit": models.Product(
            code="INS-U", name="Installation", price_unit="per_unit",
            unit_price=Decimal("50000"),
        ),
        "nolimit": models.Product(
            code="FREE-SQM", name="Unbounded Fabric", price_unit="per_sqm",
            unit_price=Decimal("200000"),
        ),
    }
    db.add_all(rows.values())
    db.commit()
    for row in rows.values():
        db.refresh(row)
    return rows


# --------------------------------------------------------------- factories
@pytest.fixture()
def make_quotation(client, customer, products):
    """Create a quotation; returns the response body."""

    def _make(headers, items=None, **overrides):
        payload = {
            "customer_id": customer.id,
            "discount_percent": 35,
            "ppn_percent": 11,
            "items": items
            if items is not None
            else [
                {"product_id": products["sqm"].id, "quantity": 3,
                 "width_cm": 200, "height_cm": 100},
                {"product_id": products["meter"].id, "quantity": 2, "width_cm": 250},
                {"product_id": products["unit"].id, "quantity": 4},
            ],
        }
        payload.update(overrides)
        response = client.post("/quotations", json=payload, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture()
def make_sales_order(client, customer, products):
    def _make(headers, items=None, **overrides):
        payload = {
            "customer_id": customer.id,
            "discount_percent": 35,
            "ppn_percent": 11,
            "items": items
            if items is not None
            else [{"product_id": products["unit"].id, "quantity": 10}],
        }
        payload.update(overrides)
        response = client.post("/sales-orders", json=payload, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture()
def confirmed_order(client, make_sales_order):
    """A sales order that can legally take payments."""

    def _make(headers, **kwargs):
        so = make_sales_order(headers, **kwargs)
        response = client.patch(
            f"/sales-orders/{so['id']}/status", json={"status": "confirmed"}, headers=headers
        )
        assert response.status_code == 200, response.text
        return response.json()

    return _make


@pytest.fixture()
def make_purchase_order(client, supplier):
    def _make(headers, items=None, **overrides):
        payload = {
            "supplier_id": supplier.id,
            "ppn_percent": 11,
            "items": items
            if items is not None
            else [{"description": "Fabric roll", "unit": "roll",
                   "quantity": 4, "unit_price": 250000}],
        }
        payload.update(overrides)
        response = client.post("/purchase-orders", json=payload, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make
