from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select

from ..auth import require_login
from ..db import get_session
from ..models import Event, User

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
def list_events(limit: int = Query(default=100, le=1000), user: User = Depends(require_login)):
    with get_session() as session:
        rows = session.exec(
            select(Event).where(Event.owner_id == user.id).order_by(Event.ts.desc()).limit(limit)
        ).all()
        return rows


@router.post("/{event_id}/ack")
def ack_event(event_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        e = session.get(Event, event_id)
        if not e or e.owner_id != user.id:
            raise HTTPException(status_code=404, detail="not_found")
        e.acknowledged = True
        session.add(e)
        session.commit()
    return {"ok": True}
