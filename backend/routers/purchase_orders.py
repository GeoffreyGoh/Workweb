"""Purchase Orders - raw materials bought from suppliers.

Linking a PO to the sales order it serves is optional, but it is what lets the
financial report attribute cost to revenue. Unlinked POs still count as
overall cost, just not against a specific order.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import auth
import models
import numbering
import pricing
import schemas
from database import get_db

router = APIRouter(prefix="/purchase-orders", tags=["purchase orders"])

EDITABLE_STATUSES = {"draft", "sent"}

ALLOWED_TRANSITIONS = {
    "draft": {"sent", "cancelled"},
    "sent": {"received", "draft", "cancelled"},
    "received": {"sent"},
    "cancelled": {"draft"},
}


def _to_out(po: models.PurchaseOrder) -> schemas.PurchaseOrderOut:
    out = schemas.PurchaseOrderOut.model_validate(po)
    if po.supplier:
        out.supplier_name = po.supplier.name
        out.supplier_code = po.supplier.code
        out.supplier_address = po.supplier.address
    if po.sales_order:
        out.so_no = po.sales_order.so_no
    if po.creator:
        out.created_by_name = po.creator.full_name
    if po.company:
        out.company_name = po.company.name
        out.company_code = po.company.code
    return out


def _apply_items(db: Session, po: models.PurchaseOrder, items) -> None:
    product_ids = {i.product_id for i in items if i.product_id}
    if product_ids:
        found = {
            p.id
            for p in db.query(models.Product.id)
            .filter(models.Product.id.in_(product_ids))
            .all()
        }
        missing = product_ids - found
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown product_id(s): {', '.join(str(i) for i in sorted(missing))}",
            )

    try:
        priced = [
            pricing.price_purchase_line(item, i) for i, item in enumerate(items, start=1)
        ]
    except pricing.PricingError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    po.items.clear()
    for line in priced:
        po.items.append(models.PurchaseOrderItem(**line))

    for field, value in pricing.compute_purchase_totals(priced, po.ppn_percent).items():
        setattr(po, field, value)


def _check_sales_order(db: Session, sales_order_id) -> None:
    if sales_order_id and not db.get(models.SalesOrder, sales_order_id):
        raise HTTPException(status_code=422, detail="Unknown sales_order_id")


@router.get("", response_model=List[schemas.PurchaseOrderListOut])
def list_purchase_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    supplier_id: Optional[int] = None,
    company_id: Optional[int] = None,
    sales_order_id: Optional[int] = None,
    q: Optional[str] = Query(None, description="Search by PO number"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.PurchaseOrder)
    if status_filter:
        query = query.filter(models.PurchaseOrder.status == status_filter)
    if supplier_id:
        query = query.filter(models.PurchaseOrder.supplier_id == supplier_id)
    if company_id:
        query = query.filter(models.PurchaseOrder.company_id == company_id)
    if sales_order_id:
        query = query.filter(models.PurchaseOrder.sales_order_id == sales_order_id)
    if q:
        query = query.filter(models.PurchaseOrder.po_no.like(f"%{q}%"))
    if date_from:
        query = query.filter(models.PurchaseOrder.order_date >= date_from)
    if date_to:
        query = query.filter(models.PurchaseOrder.order_date <= date_to)

    rows = query.order_by(models.PurchaseOrder.id.desc()).offset(offset).limit(limit).all()

    results = []
    for row in rows:
        item = schemas.PurchaseOrderListOut.model_validate(row)
        if row.supplier:
            item.supplier_name = row.supplier.name
            item.supplier_code = row.supplier.code
        if row.sales_order:
            item.so_no = row.sales_order.so_no
        if row.creator:
            item.created_by_name = row.creator.full_name
        if row.company:
            item.company_name = row.company.name
            item.company_code = row.company.code
        item.can_edit = auth.is_admin(current_user) or row.created_by == current_user.id
        results.append(item)
    return results


@router.get("/{po_id}", response_model=schemas.PurchaseOrderOut)
def get_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    po = db.get(models.PurchaseOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return _to_out(po)


@router.post("", response_model=schemas.PurchaseOrderOut, status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    payload: schemas.PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if not db.get(models.Supplier, payload.supplier_id):
        raise HTTPException(status_code=422, detail="Unknown supplier_id")
    _check_sales_order(db, payload.sales_order_id)

    company = auth.resolve_company(db, payload.company_id, current_user)
    po = models.PurchaseOrder(**payload.model_dump(exclude={"items"}))
    po.company_id = company.id
    po.order_date = payload.order_date or date.today()
    po.status = "draft"
    po.created_by = current_user.id
    _apply_items(db, po, payload.items)

    numbering.allocate(
        db, po, models.PurchaseOrder.po_no,
        numbering.scoped(numbering.PREFIXES["purchase_order"], company.code),
        po.order_date,
    )
    db.refresh(po)
    return _to_out(po)


@router.put("/{po_id}", response_model=schemas.PurchaseOrderOut)
def update_purchase_order(
    po_id: int,
    payload: schemas.PurchaseOrderUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    po = db.get(models.PurchaseOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    auth.require_owner_or_admin(current_user, po, "purchase order")
    if po.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409, detail=f"A '{po.status}' purchase order can no longer be edited"
        )
    if not db.get(models.Supplier, payload.supplier_id):
        raise HTTPException(status_code=422, detail="Unknown supplier_id")
    _check_sales_order(db, payload.sales_order_id)

    changes = payload.model_dump(exclude={"items"}, exclude_unset=True)
    changes.pop("company_id", None)
    for field, value in changes.items():
        setattr(po, field, value)

    items = payload.items if payload.items is not None else [
        schemas.PurchaseOrderItemIn(
            product_id=line.product_id,
            description=line.description,
            unit=line.unit,
            quantity=line.quantity,
            unit_price=line.unit_price,
        )
        for line in po.items
    ]
    _apply_items(db, po, items)

    db.commit()
    db.refresh(po)
    return _to_out(po)


@router.patch("/{po_id}/status", response_model=schemas.PurchaseOrderOut)
def change_status(
    po_id: int,
    payload: schemas.PurchaseOrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    po = db.get(models.PurchaseOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    auth.require_owner_or_admin(current_user, po, "purchase order")

    allowed = ALLOWED_TRANSITIONS.get(po.status, set())
    if payload.status != po.status and payload.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move a purchase order from '{po.status}' to '{payload.status}'",
        )
    po.status = payload.status
    db.commit()
    db.refresh(po)
    return _to_out(po)


@router.delete("/{po_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    po = db.get(models.PurchaseOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    auth.require_owner_or_admin(current_user, po, "purchase order")
    if po.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft purchase orders can be deleted")
    db.delete(po)
    db.commit()


# ------------------------------------------------- split across suppliers
def _split_groups(db: Session, so: models.SalesOrder):
    """Group a sales order's lines by each product's default supplier."""
    product_ids = {line.product_id for line in so.items}
    products = {
        p.id: p
        for p in db.query(models.Product).filter(models.Product.id.in_(product_ids)).all()
    } if product_ids else {}

    grouped = {}
    unassigned = []
    for line in so.items:
        product = products.get(line.product_id)
        entry = schemas.SupplierSplitLine(
            sales_order_item_id=line.id,
            product_id=line.product_id,
            product_code=line.product_code,
            product_name=line.product_name,
            quantity=line.quantity,
            measure=line.measure,
            price_unit=line.price_unit,
        )
        supplier_id = product.supplier_id if product else None
        if supplier_id is None:
            unassigned.append(entry)
        else:
            grouped.setdefault(supplier_id, []).append(entry)

    suppliers = {
        s.id: s
        for s in db.query(models.Supplier).filter(models.Supplier.id.in_(grouped)).all()
    } if grouped else {}

    groups = [
        schemas.SupplierSplitGroup(
            supplier_id=supplier_id,
            supplier_name=suppliers[supplier_id].name if supplier_id in suppliers else None,
            supplier_code=suppliers[supplier_id].code if supplier_id in suppliers else None,
            lines=lines,
        )
        for supplier_id, lines in grouped.items()
    ]
    return groups, unassigned


@router.get("/split/{sales_order_id}", response_model=schemas.PurchaseOrderSplitPreview)
def preview_split(
    sales_order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Show how a sales order would break into one purchase order per supplier."""
    so = db.get(models.SalesOrder, sales_order_id)
    if not so:
        raise HTTPException(status_code=404, detail="Sales order not found")
    groups, unassigned = _split_groups(db, so)
    return schemas.PurchaseOrderSplitPreview(
        sales_order_id=so.id, so_no=so.so_no, groups=groups, unassigned=unassigned
    )


@router.post(
    "/split/{sales_order_id}",
    response_model=List[schemas.PurchaseOrderOut],
    status_code=status.HTTP_201_CREATED,
)
def create_split(
    sales_order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Raise one draft purchase order per supplier for a sales order.

    Lines whose product has no default supplier are left out rather than
    dumped on an arbitrary vendor; the preview endpoint lists them so they can
    be assigned first.
    """
    so = db.get(models.SalesOrder, sales_order_id)
    if not so:
        raise HTTPException(status_code=404, detail="Sales order not found")
    if so.status in ("draft", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Confirm the sales order before ordering materials (it is '{so.status}')",
        )

    groups, unassigned = _split_groups(db, so)
    if not groups:
        raise HTTPException(
            status_code=409,
            detail=(
                "None of the products on this order have a default supplier set, "
                "so there is nothing to split. Set one on each product first."
            ),
        )

    created = []
    for group in groups:
        supplier = db.get(models.Supplier, group.supplier_id)
        po = models.PurchaseOrder(
            supplier_id=supplier.id,
            sales_order_id=so.id,
            company_id=so.company_id,
            order_date=date.today(),
            status="draft",
            currency=so.currency,
            payment_terms=supplier.payment_terms,
            ppn_percent=so.ppn_percent,
            notes=f"Materials for {so.so_no}",
            created_by=current_user.id,
        )
        # Quantity follows the billable measure: square metres of fabric for a
        # per_sqm blind, running metres for track, pieces otherwise.
        items = [
            schemas.PurchaseOrderItemIn(
                product_id=line.product_id,
                description=f"{line.product_name} ({line.product_code})",
                unit={"per_sqm": "m2", "per_meter": "m"}.get(line.price_unit, "pcs"),
                quantity=line.measure if line.measure > 0 else line.quantity,
                unit_price=Decimal("0"),
            )
            for line in group.lines
        ]
        _apply_items(db, po, items)
        numbering.allocate(
            db, po, models.PurchaseOrder.po_no,
            numbering.scoped(numbering.PREFIXES["purchase_order"],
                             so.company.code if so.company else None),
            po.order_date,
        )
        db.refresh(po)
        created.append(_to_out(po))

    return created
