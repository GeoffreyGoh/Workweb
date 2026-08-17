"""Sales Orders - an accepted quotation, and the document the factory works to.

Priced exactly like a quotation (same pricing.py), so converting a quotation
carries its numbers across unchanged.
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

router = APIRouter(prefix="/sales-orders", tags=["sales orders"])

EDITABLE_STATUSES = {"draft", "confirmed"}

ALLOWED_TRANSITIONS = {
    "draft": {"confirmed", "cancelled"},
    "confirmed": {"in_production", "draft", "cancelled"},
    "in_production": {"delivered", "confirmed", "cancelled"},
    "delivered": {"completed", "in_production"},
    "completed": set(),
    "cancelled": {"draft"},
}


# ------------------------------------------------------------------ helpers
def _paid(db: Session, sales_order_id: int) -> Decimal:
    total = (
        db.query(func.sum(models.Receipt.amount))
        .filter(models.Receipt.sales_order_id == sales_order_id)
        .scalar()
    )
    return pricing.money(total or 0)


def _to_out(db: Session, so: models.SalesOrder, user) -> schemas.SalesOrderOut:
    out = schemas.SalesOrderOut.model_validate(so)
    out.dp_amount, out.dp_balance = pricing.compute_dp(so.total, so.dp_percent)
    if so.customer:
        out.customer_name = so.customer.name
        out.customer_code = so.customer.code
    if so.quotation:
        out.quotation_no = so.quotation.quotation_no
    if so.creator:
        out.created_by_name = so.creator.full_name
    if so.company:
        out.company_name = so.company.name
        out.company_code = so.company.code
    out.amount_paid = _paid(db, so.id)
    out.balance_due = pricing.money(so.total - out.amount_paid)
    return out


def _apply_items(db: Session, so: models.SalesOrder, items) -> None:
    ids = {item.product_id for item in items}
    products = {}
    if ids:
        rows = db.query(models.Product).filter(models.Product.id.in_(ids)).all()
        products = {p.id: p for p in rows}
        missing = ids - set(products)
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown product_id(s): {', '.join(str(i) for i in sorted(missing))}",
            )

    try:
        priced = [
            pricing.price_line(products[item.product_id], item, so.discount_percent, i)
            for i, item in enumerate(items, start=1)
        ]
    except pricing.PricingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    so.items.clear()
    for line, submitted in zip(priced, items):
        so.items.append(models.SalesOrderItem(
            component_options=submitted.component_options, **line
        ))

    totals = pricing.compute_totals(priced, so.ppn_percent, so.installation_cost)
    for field, value in totals.items():
        setattr(so, field, value)
    so.dp_amount, _ = pricing.compute_dp(so.total, so.dp_percent)


def _fill_from_customer(so: models.SalesOrder, customer: models.Customer) -> None:
    defaults = {
        "nik_npwp": customer.nik_npwp,
        "address": customer.address,
        "deliver_to": customer.deliver_to or customer.name,
        "deliver_address": customer.deliver_address or customer.address,
        "phone": customer.phone,
        "email": customer.email,
        "price_group": customer.price_group,
        "payment_terms": customer.payment_terms,
    }
    for field, value in defaults.items():
        if not getattr(so, field):
            setattr(so, field, value)


# ------------------------------------------------------------------- routes
@router.get("", response_model=List[schemas.SalesOrderListOut])
def list_sales_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    customer_id: Optional[int] = None,
    company_id: Optional[int] = None,
    q: Optional[str] = Query(None, description="Search by SO number"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    mine_only: bool = False,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.SalesOrder)
    if status_filter:
        query = query.filter(models.SalesOrder.status == status_filter)
    if customer_id:
        query = query.filter(models.SalesOrder.customer_id == customer_id)
    if company_id:
        query = query.filter(models.SalesOrder.company_id == company_id)
    if q:
        query = query.filter(models.SalesOrder.so_no.like(f"%{q}%"))
    if date_from:
        query = query.filter(models.SalesOrder.order_date >= date_from)
    if date_to:
        query = query.filter(models.SalesOrder.order_date <= date_to)
    if mine_only:
        query = query.filter(models.SalesOrder.created_by == current_user.id)

    rows = query.order_by(models.SalesOrder.id.desc()).offset(offset).limit(limit).all()

    results = []
    for row in rows:
        item = schemas.SalesOrderListOut.model_validate(row)
        if row.customer:
            item.customer_name = row.customer.name
            item.customer_code = row.customer.code
        if row.quotation:
            item.quotation_no = row.quotation.quotation_no
        if row.creator:
            item.created_by_name = row.creator.full_name
        if row.company:
            item.company_name = row.company.name
            item.company_code = row.company.code
        item.amount_paid = _paid(db, row.id)
        item.balance_due = pricing.money(row.total - item.amount_paid)
        item.can_edit = auth.is_admin(current_user) or row.created_by == current_user.id
        results.append(item)
    return results


@router.get("/{so_id}", response_model=schemas.SalesOrderOut)
def get_sales_order(
    so_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    so = db.get(models.SalesOrder, so_id)
    if not so:
        raise HTTPException(status_code=404, detail="Sales order not found")
    return _to_out(db, so, current_user)


@router.post("", response_model=schemas.SalesOrderOut, status_code=status.HTTP_201_CREATED)
def create_sales_order(
    payload: schemas.SalesOrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    customer = db.get(models.Customer, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=422, detail="Unknown customer_id")

    company = auth.resolve_company(db, payload.company_id, current_user)
    so = models.SalesOrder(**payload.model_dump(exclude={"items"}))
    so.company_id = company.id
    so.order_date = payload.order_date or date.today()
    so.status = "draft"
    so.created_by = current_user.id
    _fill_from_customer(so, customer)
    _apply_items(db, so, payload.items)

    numbering.allocate(
        db, so, models.SalesOrder.so_no,
        numbering.scoped(numbering.PREFIXES["sales_order"], company.code),
        so.order_date,
    )
    db.refresh(so)
    return _to_out(db, so, current_user)


@router.post(
    "/from-quotation/{quotation_id}",
    response_model=schemas.SalesOrderOut,
    status_code=status.HTTP_201_CREATED,
)
def convert_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """The legacy screen calls this 'To SO'. Copies the quotation across
    verbatim and marks it converted."""
    quotation = db.get(models.Quotation, quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status == "converted":
        existing = (
            db.query(models.SalesOrder)
            .filter(models.SalesOrder.quotation_id == quotation_id)
            .first()
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Already converted to {existing.so_no}"
                if existing
                else "Quotation is already converted"
            ),
        )
    if quotation.status not in ("approved", "sent"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Only an approved or sent quotation can become a sales order "
                f"(this one is '{quotation.status}')"
            ),
        )

    so = models.SalesOrder(
        quotation_id=quotation.id,
        customer_id=quotation.customer_id,
        # The order belongs to whichever entity quoted for it.
        company_id=quotation.company_id,
        order_date=date.today(),
        status="draft",
        nik_npwp=quotation.nik_npwp,
        surveyor=quotation.surveyor,
        address=quotation.address,
        deliver_to=quotation.deliver_to,
        deliver_address=quotation.deliver_address,
        phone=quotation.phone,
        email=quotation.email,
        currency=quotation.currency,
        exchange_rate=quotation.exchange_rate,
        price_group=quotation.price_group,
        payment_terms=quotation.payment_terms,
        discount_percent=quotation.discount_percent,
        ppn_percent=quotation.ppn_percent,
        installation_cost=quotation.installation_cost,
        dp_percent=quotation.dp_percent,
        dp_amount=quotation.dp_amount,
        notes=quotation.notes,
        created_by=current_user.id,
    )

    # Copy the priced lines straight over - no repricing, the customer
    # accepted these exact numbers.
    for line in quotation.items:
        so.items.append(
            models.SalesOrderItem(
                line_no=line.line_no,
                product_id=line.product_id,
                product_code=line.product_code,
                product_name=line.product_name,
                price_unit=line.price_unit,
                description=line.description,
                quantity=line.quantity,
                width_cm=line.width_cm,
                height_cm=line.height_cm,
                measure=line.measure,
                unit_price=line.unit_price,
                component_options=line.component_options,
                line_discount_pct=line.line_discount_pct,
                line_total=line.line_total,
                line_discount_amt=line.line_discount_amt,
                line_net=line.line_net,
            )
        )
    for field in (
        "subtotal", "discount_amount", "netto", "installation_cost",
        "ppn_amount", "total", "total_qty",
    ):
        setattr(so, field, getattr(quotation, field))

    quotation.status = "converted"
    numbering.allocate(
        db, so, models.SalesOrder.so_no,
        numbering.scoped(numbering.PREFIXES["sales_order"],
                         quotation.company.code if quotation.company else None),
        so.order_date,
    )
    db.refresh(so)
    return _to_out(db, so, current_user)


@router.put("/{so_id}", response_model=schemas.SalesOrderOut)
def update_sales_order(
    so_id: int,
    payload: schemas.SalesOrderUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    so = db.get(models.SalesOrder, so_id)
    if not so:
        raise HTTPException(status_code=404, detail="Sales order not found")
    auth.require_owner_or_admin(current_user, so, "sales order")
    if so.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"A '{so.status}' sales order can no longer be edited",
        )

    customer = db.get(models.Customer, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=422, detail="Unknown customer_id")

    changes = payload.model_dump(exclude={"items"}, exclude_unset=True)
    changes.pop("company_id", None)   # the number encodes it; never reassign
    for field, value in changes.items():
        setattr(so, field, value)
    _fill_from_customer(so, customer)

    items = payload.items if payload.items is not None else [
        schemas.SalesOrderItemIn(
            product_id=line.product_id,
            description=line.description,
            quantity=line.quantity,
            width_cm=line.width_cm,
            height_cm=line.height_cm,
            unit_price=line.unit_price,
            line_discount_pct=line.line_discount_pct,
            component_options=line.component_options,
        )
        for line in so.items
    ]
    _apply_items(db, so, items)

    db.commit()
    db.refresh(so)
    return _to_out(db, so, current_user)


@router.patch("/{so_id}/status", response_model=schemas.SalesOrderOut)
def change_status(
    so_id: int,
    payload: schemas.SalesOrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    so = db.get(models.SalesOrder, so_id)
    if not so:
        raise HTTPException(status_code=404, detail="Sales order not found")
    auth.require_owner_or_admin(current_user, so, "sales order")

    allowed = ALLOWED_TRANSITIONS.get(so.status, set())
    if payload.status != so.status and payload.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move a sales order from '{so.status}' to '{payload.status}'",
        )

    # Closing an order that was never fully paid is usually a mistake.
    if payload.status == "completed":
        outstanding = pricing.money(so.total - _paid(db, so.id))
        if outstanding > 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{so.currency} {outstanding:,.2f} is still outstanding. "
                    "Record a receipt before completing this order."
                ),
            )

    so.status = payload.status
    db.commit()
    db.refresh(so)
    return _to_out(db, so, current_user)


@router.delete("/{so_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sales_order(
    so_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    so = db.get(models.SalesOrder, so_id)
    if not so:
        raise HTTPException(status_code=404, detail="Sales order not found")
    auth.require_owner_or_admin(current_user, so, "sales order")
    if so.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft sales orders can be deleted")
    if so.receipts:
        raise HTTPException(status_code=409, detail="This order already has receipts")
    if db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.sales_order_id == so_id
    ).first():
        raise HTTPException(status_code=409, detail="A purchase order references this order")

    if so.quotation_id:
        quotation = db.get(models.Quotation, so.quotation_id)
        if quotation and quotation.status == "converted":
            quotation.status = "approved"  # hand it back to the sales side
    db.delete(so)
    db.commit()
