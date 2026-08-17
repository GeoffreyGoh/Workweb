"""Per-company, per-month document numbering: PREFIX-COMPANY-YYYYMM-###.

Q-GB-202608-001, SO-GB-202608-001, PO-MJ-202608-001, RCP-GB-202608-001.

Each company runs its own sequence: two entities may both hold document 001
for a month without colliding, which is what a separate set of books needs.

The sequence is read fresh inside the create call and the column carries a
unique index, so two people saving in the same second collide loudly rather
than silently reusing a number. Callers retry via `allocate`.
"""

from datetime import date

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

PREFIXES = {
    "quotation": "Q",
    "sales_order": "SO",
    "purchase_order": "PO",
    "receipt": "RCP",
    "delivery_note": "SJ",  # Surat Jalan
}


def scoped(prefix: str, company_code=None) -> str:
    """Fold the company code into the prefix: 'Q' + 'GB' -> 'Q-GB'."""
    code = (company_code or "").strip().upper()
    return f"{prefix}-{code}" if code else prefix


def next_number(db: Session, column, prefix: str, on_date: date) -> str:
    """Next free number for `prefix` in the month of `on_date`.

    `prefix` already carries the company code (see `scoped`), so each company
    counts independently.
    """
    stem = f"{prefix}-{on_date:%Y%m}-"
    last = (
        db.query(column)
        .filter(column.like(f"{stem}%"))
        .order_by(column.desc())
        .first()
    )
    seq = 1
    if last:
        try:
            seq = int(last[0].rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            seq = 1
    return f"{stem}{seq:03d}"


def allocate(db: Session, record, column, prefix: str, on_date: date, attempts: int = 5):
    """Assign a number and commit, retrying if another session took it first."""
    for attempt in range(attempts):
        setattr(record, column.key, next_number(db, column, prefix, on_date))
        db.add(record)
        try:
            db.commit()
            return record
        except IntegrityError:
            db.rollback()
            if attempt == attempts - 1:
                raise HTTPException(
                    status_code=409,
                    detail=f"Could not allocate a {prefix} number, please retry",
                )
    return record
