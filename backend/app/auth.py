"""Minimal auth: bcrypt password hash + one 7-day JWT (no refresh token)."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from sqlmodel import Session

from backend.app.config import JWT_DAYS, JWT_SECRET
from backend.app.db import get_session
from backend.app.models import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def make_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(days=JWT_DAYS)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def get_current_user(authorization: str = Header(default=""),
                     session: Session = Depends(get_session)) -> User:
    token = authorization.removeprefix("Bearer ").strip()
    try:
        user_id = int(jwt.decode(token, JWT_SECRET, algorithms=["HS256"])["sub"])
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="请先登录")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="账号不存在")
    return user


def get_owned(session: Session, model, obj_id, user: User):
    """Fetch a row and make sure it belongs to the current user (404 otherwise)."""
    obj = session.get(model, obj_id)
    if obj is None or getattr(obj, "user_id", None) != user.id:
        raise HTTPException(status_code=404, detail="记录不存在")
    return obj
