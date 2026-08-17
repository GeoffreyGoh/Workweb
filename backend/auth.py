"""JWT issuing/validation, password hashing, and role-based access control."""

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

import models
from database import get_db

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Two kinds of account. Everyone sees every document; the only thing an
# 'admin' can do that a 'user' cannot is edit documents somebody else created.
ROLES = ("admin", "user")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(db: Session, username: str, password: str):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise credentials_error
    except JWTError:
        raise credentials_error

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not user.is_active:
        raise credentials_error
    return user


def require_role(*allowed: str):
    """Dependency factory: restrict a route to the given roles.

        @router.post("/products", dependencies=[Depends(auth.require_role("admin"))])
    """

    def checker(current_user: models.User = Depends(get_current_user)) -> models.User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(allowed)}",
            )
        return current_user

    return checker


def is_admin(user: models.User) -> bool:
    return user.role == "admin"


def require_owner_or_admin(user: models.User, document, what: str = "document") -> None:
    """Everyone may read every document, but only its author - or an admin -
    may change it. Documents with no author (legacy/imported) are admin-only."""
    if is_admin(user):
        return
    if document.created_by is not None and document.created_by == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            f"This {what} was created by someone else. "
            "Ask an admin to change it."
        ),
    )


def resolve_company(db, company_id, user: models.User) -> models.Company:
    """Which entity is issuing this document.

    Explicit choice wins; otherwise the user's default; otherwise, when only
    one company exists, that one. With several companies and no default we
    refuse rather than guess - printing a document under the wrong letterhead
    is worse than an error message.
    """
    if company_id:
        company = db.get(models.Company, company_id)
        if not company:
            raise HTTPException(status_code=422, detail="Unknown company_id")
        if not company.is_active:
            raise HTTPException(
                status_code=422, detail=f"{company.name} is no longer active"
            )
        return company

    if user.default_company_id:
        company = db.get(models.Company, user.default_company_id)
        if company and company.is_active:
            return company

    companies = (
        db.query(models.Company).filter(models.Company.is_active.is_(True)).all()
    )
    if len(companies) == 1:
        return companies[0]
    if not companies:
        raise HTTPException(
            status_code=409,
            detail="No company has been set up yet - add one before issuing documents",
        )
    raise HTTPException(
        status_code=422,
        detail="Choose which company is issuing this document",
    )
