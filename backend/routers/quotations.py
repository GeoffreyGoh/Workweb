"""Sales Quotations.

All totals are computed server-side in pricing.py; anything money-shaped that
the client sends (other than an explicit unit_price override) is ignored.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import auth
import models
import numbering
import pricing
import schemas
from database import get_db

router = APIRouter(prefix="/quotations", tags=["quotations"])

EDITABLE_STATUSES = {"draft"}

# Where a quotation may go next. 'converted' is terminal - the Sales Order
# module owns it from that point on.
ALLOWED_TRANSITIONS = {
    "draft": {"sent", "cancelled"},
    "sent": {"approved", "draft", "cancelled"},
    "approved": {"converted", "sent", "cancelled"},
    "converted": set(),
    "cancelled": {"draft"},
}


# ------------------------------------------------------------------ helpers
def _to_out(quotation: models.Quotation) -> schemas.QuotationOut:
    out = schemas.QuotationOut.model_validate(quotation)
    out.dp_amount, out.dp_balance = pricing.compute_dp(
        quotation.total, quotation.dp_percent
    )
    if quotation.customer:
        out.customer_name = quotation.customer.name
        out.customer_code = quotation.customer.code
    if quotation.creator:
        out.created_by_name = quotation.creator.full_name
    if quotation.company:
        out.company_name = quotation.company.name
        out.company_code = quotation.company.code
    return out


def _load_products(db: Session, items) -> dict:
    """Fetch every referenced product up front, so pricing is one round trip."""
    ids = {item.product_id for item in items}
    if not ids:
        return {}
    products = db.query(models.Product).filter(models.Product.id.in_(ids)).all()
    found = {p.id: p for p in products}
    missing = ids - set(found)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown product_id(s): {', '.join(str(i) for i in sorted(missing))}",
        )
    return found


def _apply_items(db: Session, quotation: models.Quotation, items) -> None:
    """Replace the quotation's lines, repricing everything from scratch."""
    products = _load_products(db, items)

    try:
        priced = [
            pricing.price_line(products[item.product_id], item, quotation.discount_percent, i)
            for i, item in enumerate(items, start=1)
        ]
    except pricing.PricingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    quotation.items.clear()
    for line, submitted in zip(priced, items):
        quotation.items.append(models.QuotationItem(
            component_options=submitted.component_options, **line
        ))

    totals = pricing.compute_totals(
        priced, quotation.ppn_percent, quotation.installation_cost
    )
    for field, value in totals.items():
        setattr(quotation, field, value)
    quotation.dp_amount, _ = pricing.compute_dp(
        quotation.total, quotation.dp_percent
    )


def _fill_from_customer(quotation: models.Quotation, customer: models.Customer) -> None:
    """Copy customer master details into any header field left blank."""
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
        if not getattr(quotation, field):
            setattr(quotation, field, value)


# ------------------------------------------------------------------- routes
@router.get("", response_model=List[schemas.QuotationListOut])
def list_quotations(
    status_filter: Optional[str] = Query(None, alias="status"),
    customer_id: Optional[int] = None,
    company_id: Optional[int] = None,
    q: Optional[str] = Query(None, description="Search by quotation number"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.Quotation)
    if status_filter:
        query = query.filter(models.Quotation.status == status_filter)
    if customer_id:
        query = query.filter(models.Quotation.customer_id == customer_id)
    if company_id:
        query = query.filter(models.Quotation.company_id == company_id)
    if q:
        query = query.filter(models.Quotation.quotation_no.like(f"%{q}%"))
    if date_from:
        query = query.filter(models.Quotation.quotation_date >= date_from)
    if date_to:
        query = query.filter(models.Quotation.quotation_date <= date_to)

    rows = (
        query.order_by(models.Quotation.id.desc()).offset(offset).limit(limit).all()
    )

    results = []
    for row in rows:
        item = schemas.QuotationListOut.model_validate(row)
        if row.customer:
            item.customer_name = row.customer.name
            item.customer_code = row.customer.code
        if row.creator:
            item.created_by_name = row.creator.full_name
        if row.company:
            item.company_name = row.company.name
            item.company_code = row.company.code
        # Lets the UI grey out rows this user may look at but not change.
        item.can_edit = auth.is_admin(current_user) or row.created_by == current_user.id
        results.append(item)
    return results


@router.get("/{quotation_id}", response_model=schemas.QuotationOut)
def get_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    quotation = db.get(models.Quotation, quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return _to_out(quotation)


@router.post("", response_model=schemas.QuotationOut, status_code=status.HTTP_201_CREATED)
def create_quotation(
    payload: schemas.QuotationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    customer = db.get(models.Customer, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=422, detail="Unknown customer_id")
    company = auth.resolve_company(db, payload.company_id, current_user)

    header = payload.model_dump(exclude={"items"})
    quotation = models.Quotation(**header)
    quotation.company_id = company.id
    quotation.quotation_date = payload.quotation_date or date.today()
    quotation.status = "draft"
    quotation.created_by = current_user.id
    _fill_from_customer(quotation, customer)

    _apply_items(db, quotation, payload.items)

    numbering.allocate(
        db,
        quotation,
        models.Quotation.quotation_no,
        numbering.scoped(numbering.PREFIXES["quotation"], company.code),
        quotation.quotation_date,
    )
    db.refresh(quotation)
    return _to_out(quotation)


@router.put("/{quotation_id}", response_model=schemas.QuotationOut)
def update_quotation(
    quotation_id: int,
    payload: schemas.QuotationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    quotation = db.get(models.Quotation, quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    auth.require_owner_or_admin(current_user, quotation, "quotation")
    if quotation.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Only draft quotations can be edited (this one is '{quotation.status}')",
        )

    customer = db.get(models.Customer, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=422, detail="Unknown customer_id")

    changes = payload.model_dump(exclude={"items"}, exclude_unset=True)
    new_company = changes.pop("company_id", None)
    if new_company and new_company != quotation.company_id:
        # The number carries the company code, so it would no longer match.
        raise HTTPException(
            status_code=409,
            detail=(
                f"{quotation.quotation_no} was issued by "
                f"{quotation.company.name if quotation.company else 'another company'}. "
                "Create a new quotation to quote under a different company."
            ),
        )
    for field, value in changes.items():
        setattr(quotation, field, value)
    _fill_from_customer(quotation, customer)

    # Header discount/PPN may have moved, so reprice even if lines are unchanged.
    items = payload.items if payload.items is not None else [
        schemas.QuotationItemIn(
            product_id=line.product_id,
            description=line.description,
            quantity=line.quantity,
            width_cm=line.width_cm,
            height_cm=line.height_cm,
            unit_price=line.unit_price,
            line_discount_pct=line.line_discount_pct,
            component_options=line.component_options,
        )
        for line in quotation.items
    ]
    _apply_items(db, quotation, items)

    db.commit()
    db.refresh(quotation)
    return _to_out(quotation)


@router.patch("/{quotation_id}/status", response_model=schemas.QuotationOut)
def change_status(
    quotation_id: int,
    payload: schemas.StatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    quotation = db.get(models.Quotation, quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    auth.require_owner_or_admin(current_user, quotation, "quotation")

    allowed = ALLOWED_TRANSITIONS.get(quotation.status, set())
    if payload.status != quotation.status and payload.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move a quotation from '{quotation.status}' to '{payload.status}'",
        )

    quotation.status = payload.status
    if payload.status == "sent":
        quotation.last_follow_up = date.today()

    db.commit()
    db.refresh(quotation)
    return _to_out(quotation)


@router.delete("/{quotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quotation(
    quotation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    quotation = db.get(models.Quotation, quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    auth.require_owner_or_admin(current_user, quotation, "quotation")
    if quotation.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft quotations can be deleted")
    if db.query(models.SalesOrder).filter(
        models.SalesOrder.quotation_id == quotation_id
    ).first():
        raise HTTPException(
            status_code=409, detail="A sales order was raised from this quotation"
        )
    db.delete(quotation)
    db.commit()
