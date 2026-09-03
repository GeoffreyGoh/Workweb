"""Receipts - money received against an invoice (kwitansi).

A receipt is a record of payment, so it is deliberately hard to change: it can
be created and (by its author or an admin) deleted, but not edited. Correcting
one means voiding it and issuing another, which is what an auditor expects.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
import numbering
import pricing
import schemas
from database import get_db

router = APIRouter(prefix="/receipts", tags=["receipts"])


def _to_out(receipt: models.Receipt, user) -> schemas.ReceiptOut:
    out = schemas.ReceiptOut.model_validate(receipt)
    if receipt.sales_order:
        out.so_no = receipt.sales_order.so_no
        if receipt.sales_order.customer:
            out.customer_name = receipt.sales_order.customer.name
    if receipt.creator:
        out.created_by_name = receipt.creator.full_name
    if receipt.company:
        out.company_name = receipt.company.name
        out.company_code = receipt.company.code
    out.can_edit = auth.is_admin(user) or receipt.created_by == user.id
    return out


@router.get("", response_model=List[schemas.ReceiptOut])
def list_receipts(
    sales_order_id: Optional[int] = None,
    company_id: Optional[int] = None,
    q: Optional[str] = Query(None, description="Search by receipt number"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.Receipt)
    if sales_order_id:
        query = query.filter(models.Receipt.sales_order_id == sales_order_id)
    if company_id:
        query = query.filter(models.Receipt.company_id == company_id)
    if q:
        query = query.filter(models.Receipt.receipt_no.like(f"%{q}%"))
    if date_from:
        query = query.filter(models.Receipt.receipt_date >= date_from)
    if date_to:
        query = query.filter(models.Receipt.receipt_date <= date_to)

    rows = query.order_by(models.Receipt.id.desc()).offset(offset).limit(limit).all()
    return [_to_out(r, current_user) for r in rows]


@router.get("/{receipt_id}", response_model=schemas.ReceiptOut)
def get_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    receipt = db.get(models.Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return _to_out(receipt, current_user)


@router.post("", response_model=schemas.ReceiptOut, status_code=status.HTTP_201_CREATED)
def create_receipt(
    payload: schemas.ReceiptCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    so = db.get(models.SalesOrder, payload.sales_order_id)
    if not so:
        raise HTTPException(status_code=422, detail="Unknown sales_order_id")
    if so.status in ("draft", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Confirm the invoice before recording payment (it is '{so.status}')",
        )

    already = db.query(func.sum(models.Receipt.amount)).filter(
        models.Receipt.sales_order_id == so.id
    ).scalar() or Decimal("0")
    outstanding = pricing.money(so.total - Decimal(str(already)))

    amount = pricing.money(payload.amount)
    if amount > outstanding:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Payment {so.currency} {amount:,.2f} exceeds the outstanding balance "
                f"of {so.currency} {outstanding:,.2f}"
            ),
        )

    receipt = models.Receipt(
        sales_order_id=so.id,
        company_id=so.company_id,      # the entity that was paid

        receipt_date=payload.receipt_date or date.today(),
        amount=amount,
        payment_method=payload.payment_method,
        reference=payload.reference,
        received_from=payload.received_from or (so.customer.name if so.customer else None),
        notes=payload.notes,
        created_by=current_user.id,
    )

    numbering.allocate(
        db,
        receipt,
        models.Receipt.receipt_no,
        numbering.scoped(numbering.PREFIXES["receipt"],
                         so.company.code if so.company else None),
        receipt.receipt_date,
    )
    db.refresh(receipt)
    return _to_out(receipt, current_user)


@router.delete("/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
def void_receipt(
    receipt_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    receipt = db.get(models.Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    auth.require_owner_or_admin(current_user, receipt, "receipt")
    if receipt.sales_order and receipt.sales_order.status == "completed":
        raise HTTPException(
            status_code=409,
            detail="Reopen the invoice before voiding one of its receipts",
        )
    so = receipt.sales_order
    db.delete(receipt)
    db.flush()

    # Voiding a payment puts money back on the account, so a receivable that
    # was closed as settled is no longer settled. Reopen it rather than let
    # the debt disappear from the outstanding list.
    if so is not None and so.receivable_closed_at is not None:
        still_owed = pricing.money(
            so.total
            - (db.query(func.sum(models.Receipt.amount))
               .filter(models.Receipt.sales_order_id == so.id).scalar() or 0)
        )
        if still_owed > 0:
            so.receivable_closed_at = None
            so.receivable_closed_by = None
            so.receivable_close_note = None

    db.commit()
