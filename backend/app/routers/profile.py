from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import select

from ..auth import require_login
from ..db import get_session
from ..models import User
from ..services.uploads import delete_image, full_path, save_image

router = APIRouter(tags=["profile"])


class BioIn(BaseModel):
    bio: str = ""


@router.put("/api/me")
def update_me(payload: BioIn, user: User = Depends(require_login)):
    with get_session() as session:
        db_user = session.get(User, user.id)
        db_user.bio = payload.bio.strip()[:1000] or None
        session.add(db_user)
        session.commit()
    return {"ok": True}


@router.post("/api/me/avatar")
async def upload_avatar(file: UploadFile = File(...), user: User = Depends(require_login)):
    relative_path, mime_type = await save_image(file, "avatars")
    with get_session() as session:
        db_user = session.get(User, user.id)
        old_path = db_user.avatar_path
        db_user.avatar_path = relative_path
        db_user.avatar_mime = mime_type
        session.add(db_user)
        session.commit()
    delete_image(old_path)
    return {"ok": True}


@router.delete("/api/me/avatar")
def delete_avatar(user: User = Depends(require_login)):
    with get_session() as session:
        db_user = session.get(User, user.id)
        old_path = db_user.avatar_path
        db_user.avatar_path = None
        db_user.avatar_mime = None
        session.add(db_user)
        session.commit()
    delete_image(old_path)
    return {"ok": True}


@router.get("/api/users/{user_id}/avatar")
def get_avatar(user_id: int, _: User = Depends(require_login)):
    with get_session() as session:
        target = session.get(User, user_id)
        if not target or not target.avatar_path:
            raise HTTPException(status_code=404, detail="not_found")
        return FileResponse(full_path(target.avatar_path), media_type=target.avatar_mime)


@router.get("/api/users")
def list_users_public(_: User = Depends(require_login)):
    """Minimal, non-sensitive directory (username + whether they have an
    avatar) — used so any signed-in user can see who else is on the
    server without exposing the admin-only overview data."""
    with get_session() as session:
        users = session.exec(select(User)).all()
        return [
            {"id": u.id, "username": u.username, "has_avatar": bool(u.avatar_path), "bio": u.bio}
            for u in users
        ]
