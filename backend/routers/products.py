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
    """
    exists = db.query(models.Product).filter(models.Product.code == payload.code).first()
    if exists:
        raise HTTPException(status_code=409, detail=f"Product code '{payload.code}' already exists")

    # spareparts is a nested list, not a plain column - build it into
    # relationship objects rather than passing it straight to the model
    # constructor (which only accepts column kwargs).
    data = payload.model_dump(exclude={"spareparts"})
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
    """Edit a product, or retire it with is_active=false. Admin only."""
    product = db.get(models.Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    updates = payload.model_dump(exclude_unset=True, exclude={"spareparts"})
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
