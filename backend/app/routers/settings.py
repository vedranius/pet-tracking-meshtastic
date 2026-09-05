from fastapi import APIRouter, Depends, HTTPException

from ..auth import hash_password, require_login, validate_password
from ..db import get_session
from ..models import User
from ..schemas import PasswordIn, SettingsIn
from ..services.telegram import get_setting, send_telegram, set_setting

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(user: User = Depends(require_login)):
    with get_session() as session:
        return {
            "telegram_bot_token": get_setting(session, user.id, "telegram_bot_token") or "",
            "telegram_chat_id": get_setting(session, user.id, "telegram_chat_id") or "",
            "language": user.language,
        }


@router.put("")
def update_settings(payload: SettingsIn, user: User = Depends(require_login)):
    with get_session() as session:
        for key, value in payload.model_dump(exclude_none=True).items():
            set_setting(session, user.id, key, value)
        session.commit()
    return {"ok": True}


@router.put("/language")
def update_language(language: str, user: User = Depends(require_login)):
    if language not in ("hr", "en"):
        raise HTTPException(status_code=400, detail="unsupported_language")
    with get_session() as session:
        db_user = session.get(User, user.id)
        db_user.language = language
        session.add(db_user)
        session.commit()
    return {"ok": True}


@router.post("/telegram/test")
async def test_telegram(user: User = Depends(require_login)):
    with get_session() as session:
        ok = await send_telegram(session, user.id, "✅ PawTrack — test message / test poruka!")
    return {"ok": ok}


@router.put("/password")
def change_password(payload: PasswordIn, user: User = Depends(require_login)):
    validate_password(payload.password)
    with get_session() as session:
        db_user = session.get(User, user.id)
        db_user.password_hash = hash_password(payload.password)
        session.add(db_user)
        session.commit()
    return {"ok": True}
