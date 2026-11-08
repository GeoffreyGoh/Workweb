"""Product master. Everyone can read; only admin can create or edit."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import get_db

router = APIRouter(prefix="/products", tags=["products"])


def _to_out(product: models.Product) -> schemas.ProductOut:
    out = schemas.ProductOut.model_validate(product)
    if product.supplier:
        out.supplier_name = product.supplier.name
    # Only offer combinations the fabric can actually be made in.
    out.options = [
        schemas.ProductOptionOut.model_validate(o)
        for o in product.options
        if o.is_available
    ]
    # Retired spareparts stay in the database (so old quotations that
    # already reference them keep their price history) but are hidden
    # from the picker, same as is_active elsewhere in this app.
    out.spareparts = [
        schemas.ProductSparepartOut.model_validate(s)
        for s in product.spareparts
        if s.is_active
    ]
    return out


@router.get("", response_model=List[schemas.ProductOut])
def list_products(
    q: Optional[str] = Query(None, description="Search by code or name"),
    active_only: bool = True,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.Product)
    if active_only:
        query = query.filter(models.Product.is_active.is_(True))
    if q:
        term = f"%{q}%"
        # ilike for the same reason as customers.py - LIKE is case-sensitive
        # on Postgres but not on MySQL's default collation.
        query = query.filter(
            or_(models.Product.code.ilike(term), models.Product.name.ilike(term))
        )
    rows = query.order_by(models.Product.name).offset(offset).limit(limit).all()
    return [_to_out(row) for row in rows]


def _next_supplier_code(db: Session) -> str:
    """Next free SUPP-### code, same scheme as _next_customer_code in
    quotations.py. Used only when a supplier is auto-created by name from
    the Add Product form - a supplier created through a (future) proper
    Suppliers admin page would supply its own code instead.
    """
    last = (
        db.query(models.Supplier.code)
        .filter(models.Supplier.code.like("SUPP-%"))
        .order_by(models.Supplier.code.desc())
        .first()
    )
    seq = 1
    if last:
        try:
            seq = int(last[0].rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            seq = 1
    return f"SUPP-{seq:03d}"


def _find_or_create_supplier(db: Session, name: str) -> models.Supplier:
    """Auto-save flow for a supplier typed directly on the Add Product
    form instead of picked from the dropdown.

    Matching rule: same name (case-insensitive) reuses the existing
    supplier; no match creates a new one. Unlike customers there is no
    second distinguishing field (no site/location concept for a
    supplier), so name alone is the key - this is deliberately simpler
    than _find_or_create_customer in quotations.py.
    """
    name = name.strip()
    existing = (
        db.query(models.Supplier)
        .filter(models.Supplier.name.ilike(name))
        .first()
    )
    if existing:
        return existing

    supplier = models.Supplier(code=_next_supplier_code(db), name=name)
    db.add(supplier)
    db.flush()  # assign supplier.id without a separate commit
    return supplier


def _duplicate_product_query(db: Session, code, name, category, exclude_id=None):
    """A product is a duplicate only when code, name, AND category all
    match - any one field differing makes it a genuinely different
    catalogue entry (Geoffrey's explicit choice: "can be doubled unless
    same"). category is nullable, so None must compare equal to None
    here explicitly - the database's own UniqueConstraint on these three
    columns does NOT catch that case (SQL treats NULL as never equal to
    another NULL), so this check is the real enforcement for a
    no-category product; the DB constraint is a backstop for everything
    else, not the primary guard.
    """
    query = db.query(models.Product).filter(
        models.Product.code == code,
        models.Product.name == name,
    )
    if category is None:
        query = query.filter(models.Product.category.is_(None))
    else:
        query = query.filter(models.Product.category == category)
    if exclude_id is not None:
        query = query.filter(models.Product.id != exclude_id)
    return query


@router.get("/{product_id}", response_model=schemas.ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    product = db.get(models.Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return _to_out(product)


@router.post("", response_model=schemas.ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: schemas.ProductCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role("admin")),
):
    """Add a product to the catalogue. Admin only.

    The price list is what every quotation is built from, so a wrong code or
    price leaks into every document that uses it. Sales staff pick from the
    catalogue; only an admin decides what is in it.

    code alone is no longer required to be globally unique - the same code
    can be reused across genuinely different products (e.g. a shared
    supplier SKU). Only an exact code+name+category match is rejected, as
    that combination is the same catalogue entry in every practical sense.
    """
    exists = _duplicate_product_query(db, payload.code, payload.name, payload.category).first()
    if exists:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A product with code '{payload.code}', name '{payload.name}' and "
                f"category '{payload.category or '(none)'}' already exists. Change "
                "at least one of those three to add it as a distinct product."
            ),
        )

    # spareparts is a nested list, not a plain column - build it into
    # relationship objects rather than passing it straight to the model
    # constructor (which only accepts column kwargs).
    data = payload.model_dump(exclude={"spareparts", "supplier_name"})
    if not data.get("supplier_id") and payload.supplier_name:
        data["supplier_id"] = _find_or_create_supplier(db, payload.supplier_name).id
    product = models.Product(**data)
    product.spareparts = [
        models.ProductSparepart(**sp.model_dump()) for sp in payload.spareparts
    ]
    db.add(product)
    db.commit()
    db.refresh(product)
    return _to_out(product)


@router.put("/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int,
    payload: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role("admin")),
):
    """Edit a product, or retire it with is_active=false. Admin only.

    code itself cannot be changed here (not in ProductUpdate) - but name
    and category can, so an edit could still collide with another
    existing product that already shares this one's code - checked the
    same way create_product does, excluding this product's own row.
    """
    product = db.get(models.Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    new_name = payload.name if payload.name is not None else product.name
    new_category = payload.category if "category" in payload.model_fields_set else product.category
    duplicate = _duplicate_product_query(
        db, product.code, new_name, new_category, exclude_id=product.id
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A product with code '{product.code}', name '{new_name}' and "
                f"category '{new_category or '(none)'}' already exists. Change "
                "at least one of those three, or edit the existing one instead."
            ),
        )

    updates = payload.model_dump(exclude_unset=True, exclude={"spareparts", "supplier_name"})
    if not updates.get("supplier_id") and payload.supplier_name:
        updates["supplier_id"] = _find_or_create_supplier(db, payload.supplier_name).id
    for field, value in updates.items():
        setattr(product, field, value)

    # spareparts omitted entirely (None) means "leave as-is"; an explicit
    # list - even an empty one - replaces the whole set. Replacing rather
    # than diffing matches how the admin screen always resends the full
    # list on every save (same as options/colors import does).
    if payload.spareparts is not None:
        product.spareparts = [
            models.ProductSparepart(**sp.model_dump()) for sp in payload.spareparts
        ]

    db.commit()
    db.refresh(product)
    return _to_out(product)


@router.get("/{product_id}/options", response_model=List[schemas.ProductOptionOut])
def product_options(
    product_id: int,
    include_unavailable: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Mechanisms and rails this fabric can be made in (FABRIC CHART).

    Unavailable combinations are hidden by default: offering a customer a
    Classic Roman in a fabric the mill will not make it in is worse than
    offering nothing.
    """
    product = db.get(models.Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return [
        schemas.ProductOptionOut.model_validate(option)
        for option in product.options
        if include_unavailable or option.is_available
    ]


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_role("admin")),
):
    """Permanently remove a product. Admin only.

    Only allowed when the product has never been used on a real document -
    a quotation, invoice, or purchase order line references it by
    product_id, and none of those tables cascade-delete when a product
    goes away. Refusing here is the only way to guarantee a hard delete
    never breaks or silently orphans a historical document; retiring it
    (is_active=false, already on the edit form) is the right move for
    anything that has actually been quoted or ordered.
    """
    product = db.get(models.Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    in_use = (
        db.query(models.QuotationItem.id)
        .filter(models.QuotationItem.product_id == product_id)
        .first()
        or db.query(models.SalesOrderItem.id)
        .filter(models.SalesOrderItem.product_id == product_id)
        .first()
        or db.query(models.PurchaseOrderItem.id)
        .filter(models.PurchaseOrderItem.product_id == product_id)
        .first()
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail=(
                f"'{product.name}' has already been used on a quotation, invoice, "
                "or purchase order and cannot be deleted. Set it to inactive "
                "instead - it will disappear from pickers but existing documents "
                "keep their history."
            ),
        )

    db.delete(product)
    db.commit()
