from __future__ import annotations

import uuid
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, Request, status

from fichas.db import get_db
from fichas.models import User
from fichas.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="session")

SESSION_COOKIE_NAME = "session"


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_session_token(user_id: uuid.UUID) -> str:
    payload = {"user_id": str(user_id)}
    return serializer.dumps(payload)


def decode_session_token(token: str) -> Optional[uuid.UUID]:
    try:
        payload = serializer.loads(token, max_age=settings.SESSION_EXPIRES_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    raw = payload.get("user_id")
    if not raw:
        return None
    return uuid.UUID(str(raw))


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    user_id = decode_session_token(token)
    if not user_id:
        return None
    return db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user_optional(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
