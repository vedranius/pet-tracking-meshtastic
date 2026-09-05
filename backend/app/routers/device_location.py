"""Location ingestion for the Android companion app. A user's phone posts
its own GPS fix here periodically (foreground service, works while the app
is backgrounded) — this is what lets an admin see how far a pet is from the
person sharing location with them, and is unrelated to the Meshtastic
trackers themselves."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from ..auth import require_login
from ..db import get_session
from ..models import DeviceLocation, User
from ..schemas import DeviceLocationIn
from ..services.ws_manager import ws_manager

router = APIRouter(prefix="/api/device-location", tags=["device-location"])


@router.post("")
async def push_device_location(payload: DeviceLocationIn, user: User = Depends(require_login)):
    if not user.location_sharing_enabled:
        # Only an admin can turn this back on (see routers/admin.py) — the
        # Android app has no on/off control of its own, so this only fires
        # while an admin has deliberately disabled it for this account.
        raise HTTPException(status_code=403, detail="location_sharing_disabled")
    with get_session() as session:
        loc = DeviceLocation(owner_id=user.id, **payload.model_dump())
        session.add(loc)
        session.commit()
        session.refresh(loc)

    await ws_manager.broadcast_admin({
        "type": "device_location",
        "owner_id": user.id,
        "username": user.username,
        "lat": loc.lat,
        "lon": loc.lon,
        "accuracy": loc.accuracy,
        "battery": loc.battery,
        "ts": loc.ts.isoformat(),
    })
    return {"ok": True}


@router.get("/me")
def my_last_location(user: User = Depends(require_login)):
    with get_session() as session:
        loc = session.exec(
            select(DeviceLocation).where(DeviceLocation.owner_id == user.id).order_by(DeviceLocation.ts.desc())
        ).first()
        return loc
