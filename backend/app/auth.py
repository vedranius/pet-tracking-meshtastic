import re

import bcrypt
from fastapi import HTTPException, Request
from sqlmodel import select

from .db import get_session
from .models import User

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def validate_username(username: str) -> None:
    if not USERNAME_RE.match(username or ""):
        raise HTTPException(status_code=400, detail="invalid_username")


def validate_password(password: str) -> None:
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="password_too_short")


def register_user(username: str, password: str) -> User:
    validate_username(username)
    validate_password(password)
    with get_session() as session:
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            raise HTTPException(status_code=409, detail="username_taken")
        is_first = session.exec(select(User)).first() is None
        user = User(
            username=username,
            password_hash=hash_password(password),
            role="admin" if is_first else "user",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def require_login(request: Request) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="not_authenticated")
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=401, detail="not_authenticated")
        return user


def require_admin(request: Request) -> User:
    user = require_login(request)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin_only")
    return user
