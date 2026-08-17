"""Customer master. Everyone can read; sales and admin can create or edit."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import get_db

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=List[schemas.CustomerOut])
def list_customers(
    q: Optional[str] = Query(None, description="Search by code or name"),
    active_only: bool = True,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.Customer)
    if active_only:
        query = query.filter(models.Customer.is_active.is_(True))
    if q:
        term = f"%{q}%"
        query = query.filter(
            or_(models.Customer.code.like(term), models.Customer.name.like(term))
        )
    return query.order_by(models.Customer.name).offset(offset).limit(limit).all()


@router.get("/{customer_id}", response_model=schemas.CustomerOut)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.post("", response_model=schemas.CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: schemas.CustomerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    exists = db.query(models.Customer).filter(models.Customer.code == payload.code).first()
    if exists:
        raise HTTPException(
            status_code=409, detail=f"Customer code '{payload.code}' already exists"
        )

    customer = models.Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.put("/{customer_id}", response_model=schemas.CustomerOut)
def update_customer(
    customer_id: int,
    payload: schemas.CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)

    db.commit()
    db.refresh(customer)
    return customer
