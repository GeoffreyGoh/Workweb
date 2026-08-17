"""Staff list, used by the report filters."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import get_db

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=List[schemas.UserOut])
def list_users(
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Everyone can see who their colleagues are - the sales report filters
    by salesperson, so the list has to be readable by all."""
    query = db.query(models.User)
    if active_only:
        query = query.filter(models.User.is_active.is_(True))
    return query.order_by(models.User.full_name).all()
