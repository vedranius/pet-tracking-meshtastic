from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import select

from ..auth import register_user, require_login, verify_password
from ..db import get_session
from ..models import User
from ..schemas import LoginIn, RegisterIn

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/register")
def register(payload: RegisterIn, request: Request):
    user = register_user(payload.username.strip(), payload.password)
    request.session["user_id"] = user.id
    return {"ok": True, "username": user.username, "role": user.role}


@router.post("/login")
def login(payload: LoginIn, request: Request):
    with get_session() as session:
        user = session.exec(select(User).where(User.username == payload.username)).first()
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="invalid_credentials")
        request.session["user_id"] = user.id
        return {"ok": True, "username": user.username, "role": user.role}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return {"authenticated": False}
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            return {"authenticated": False}
        return {
            "authenticated": True,
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "language": user.language,
            "bio": user.bio,
            "has_avatar": bool(user.avatar_path),
        }
