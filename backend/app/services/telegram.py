import logging

import httpx
from sqlmodel import Session, select

from ..models import Setting

log = logging.getLogger("pawtrack.telegram")


def _key(owner_id: int, name: str) -> str:
    return f"{owner_id}:{name}"


def get_setting(session: Session, owner_id: int, name: str) -> str | None:
    row = session.get(Setting, _key(owner_id, name))
    return row.value if row and row.value else None


def set_setting(session: Session, owner_id: int, name: str, value: str) -> None:
    key = _key(owner_id, name)
    row = session.get(Setting, key)
    if row:
        row.value = value
    else:
        row = Setting(key=key, value=value)
    session.add(row)


async def send_telegram(session: Session, owner_id: int, text: str) -> bool:
    token = get_setting(session, owner_id, "telegram_bot_token")
    chat_id = get_setting(session, owner_id, "telegram_chat_id")
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                url,
                data={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "false"},
            )
            r.raise_for_status()
            return True
    except Exception as e:
        log.warning("telegram send failed: %s", e)
        return False
