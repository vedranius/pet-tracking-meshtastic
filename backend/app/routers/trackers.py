import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import select

from ..auth import require_login
from ..db import get_session
from ..models import Channel, Event, Gateway, PetPhoto, Position, Telemetry, Tracker, User
from ..schemas import BuzzerConfigIn, PositionConfigIn, PowerConfigIn, RingIn, TrackerIn
from ..services import mesh_admin
from ..services.mesh_manager import mesh_manager
from ..services.timerange import resolve_range
from ..services.uploads import delete_image, full_path, save_image

log = logging.getLogger("pawtrack.trackers")

router = APIRouter(prefix="/api/trackers", tags=["trackers"])


def _user_gateway_ids(session, owner_id: int) -> list[int]:
    return [g.id for g in session.exec(select(Gateway).where(Gateway.owner_id == owner_id)).all()]


def _own_tracker(session, tracker_id: int, owner_id: int) -> Tracker:
    t = session.get(Tracker, tracker_id)
    if not t or t.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="not_found")
    return t


@router.get("")
def list_trackers(user: User = Depends(require_login)):
    with get_session() as session:
        return session.exec(select(Tracker).where(Tracker.owner_id == user.id)).all()


@router.post("")
def create_tracker(payload: TrackerIn, user: User = Depends(require_login)):
    with get_session() as session:
        t = Tracker(owner_id=user.id, **payload.model_dump())
        session.add(t)
        session.commit()
        session.refresh(t)
        return t


@router.put("/{tracker_id}")
def update_tracker(tracker_id: int, payload: TrackerIn, user: User = Depends(require_login)):
    with get_session() as session:
        t = _own_tracker(session, tracker_id, user.id)
        for k, v in payload.model_dump().items():
            setattr(t, k, v)
        session.add(t)
        session.commit()
        session.refresh(t)
        return t


@router.delete("/{tracker_id}")
def delete_tracker(tracker_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        t = _own_tracker(session, tracker_id, user.id)
        session.delete(t)
        session.commit()
    return {"ok": True}


@router.get("/{tracker_id}/positions")
def tracker_positions(
    tracker_id: int,
    hours: int = Query(default=24, le=24 * 30),
    date: str | None = Query(default=None, description="YYYY-MM-DD (UTC) — overrides `hours` to one specific day"),
    user: User = Depends(require_login),
):
    since, until = resolve_range(hours, date)
    with get_session() as session:
        _own_tracker(session, tracker_id, user.id)
        stmt = select(Position).where(Position.tracker_id == tracker_id, Position.ts >= since)
        if until:
            stmt = stmt.where(Position.ts < until)
        return session.exec(stmt.order_by(Position.ts)).all()


@router.get("/{tracker_id}/telemetry")
def tracker_telemetry(tracker_id: int, hours: int = Query(default=24, le=24 * 30), user: User = Depends(require_login)):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with get_session() as session:
        _own_tracker(session, tracker_id, user.id)
        rows = session.exec(
            select(Telemetry)
            .where(Telemetry.tracker_id == tracker_id, Telemetry.ts >= since)
            .order_by(Telemetry.ts)
        ).all()
        return rows


@router.post("/{tracker_id}/ring")
def ring_tracker(tracker_id: int, payload: RingIn, user: User = Depends(require_login)):
    with get_session() as session:
        t = _own_tracker(session, tracker_id, user.id)
        if not t.node_id:
            raise HTTPException(status_code=400, detail="no_node_assigned")
        channel_index = 0
        if t.channel_id:
            ch = session.get(Channel, t.channel_id)
            if ch:
                channel_index = ch.device_index
        gw_ids = _user_gateway_ids(session, user.id)

    interface = mesh_manager.get_active_interface(gateway_ids=gw_ids)
    if interface is None:
        raise HTTPException(status_code=503, detail="no_gateway_connected")

    text = payload.text or f"\U0001f514 {t.name}"
    try:
        mesh_admin.ring(interface, t.node_id, channel_index, text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"send_failed: {e}")

    with get_session() as session:
        session.add(Event(owner_id=user.id, tracker_id=tracker_id, type="ring_sent", message=f"ring_sent::{t.name}"))
        session.commit()
    return {"ok": True}


@router.post("/{tracker_id}/push-position-config")
def push_position_config(tracker_id: int, payload: PositionConfigIn, user: User = Depends(require_login)):
    with get_session() as session:
        t = _own_tracker(session, tracker_id, user.id)
        if not t.node_id:
            raise HTTPException(status_code=400, detail="no_node_assigned")
        gw_ids = _user_gateway_ids(session, user.id)

    interface = mesh_manager.get_active_interface(gateway_ids=gw_ids)
    if interface is None:
        raise HTTPException(status_code=503, detail="no_gateway_connected")

    try:
        mesh_admin.push_position_config(
            interface, t.node_id, payload.gps_update_interval, payload.broadcast_secs,
            payload.smart_min_distance, payload.smart_min_interval,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"push_failed: {e}")
    return {"ok": True}


@router.post("/{tracker_id}/push-power-config")
def push_power_config(tracker_id: int, payload: PowerConfigIn, user: User = Depends(require_login)):
    with get_session() as session:
        t = _own_tracker(session, tracker_id, user.id)
        if not t.node_id:
            raise HTTPException(status_code=400, detail="no_node_assigned")
        gw_ids = _user_gateway_ids(session, user.id)

    interface = mesh_manager.get_active_interface(gateway_ids=gw_ids)
    if interface is None:
        raise HTTPException(status_code=503, detail="no_gateway_connected")

    try:
        mesh_admin.push_power_config(interface, t.node_id, payload.is_power_saving, payload.ls_secs)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"push_failed: {e}")
    return {"ok": True}


@router.post("/{tracker_id}/push-buzzer-config")
def push_buzzer_config(tracker_id: int, payload: BuzzerConfigIn, user: User = Depends(require_login)):
    with get_session() as session:
        t = _own_tracker(session, tracker_id, user.id)
        if not t.node_id:
            raise HTTPException(status_code=400, detail="no_node_assigned")
        gw_ids = _user_gateway_ids(session, user.id)

    interface = mesh_manager.get_active_interface(gateway_ids=gw_ids)
    if interface is None:
        raise HTTPException(status_code=503, detail="no_gateway_connected")

    try:
        mesh_admin.push_buzzer_mode(interface, t.node_id, payload.buzzer_mode)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"push_failed: {e}")
    return {"ok": True}


# -- photos -----------------------------------------------------------
# Visible to every signed-in user, not just the owner/admin — the point of
# a pet photo is helping someone recognize the animal if it's ever found
# by a stranger, so it deliberately isn't scoped by ownership like
# everything else in this router.

@router.get("/{tracker_id}/photos")
def list_pet_photos(tracker_id: int, _: User = Depends(require_login)):
    with get_session() as session:
        if not session.get(Tracker, tracker_id):
            raise HTTPException(status_code=404, detail="not_found")
        return session.exec(
            select(PetPhoto).where(PetPhoto.tracker_id == tracker_id).order_by(PetPhoto.created_at)
        ).all()


@router.post("/{tracker_id}/photos")
async def upload_pet_photo(tracker_id: int, file: UploadFile = File(...), user: User = Depends(require_login)):
    with get_session() as session:
        t = _own_tracker(session, tracker_id, user.id)
        relative_path, mime_type = await save_image(file, f"pets/{t.id}")
        photo = PetPhoto(tracker_id=t.id, path=relative_path, mime_type=mime_type)
        session.add(photo)
        session.commit()
        session.refresh(photo)
        return photo


@router.delete("/{tracker_id}/photos/{photo_id}")
def delete_pet_photo(tracker_id: int, photo_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        _own_tracker(session, tracker_id, user.id)
        photo = session.get(PetPhoto, photo_id)
        if not photo or photo.tracker_id != tracker_id:
            raise HTTPException(status_code=404, detail="not_found")
        path = photo.path
        session.delete(photo)
        session.commit()
    delete_image(path)
    return {"ok": True}


@router.get("/{tracker_id}/photos/{photo_id}/file")
def get_pet_photo_file(tracker_id: int, photo_id: int, _: User = Depends(require_login)):
    with get_session() as session:
        photo = session.get(PetPhoto, photo_id)
        if not photo or photo.tracker_id != tracker_id:
            raise HTTPException(status_code=404, detail="not_found")
        return FileResponse(full_path(photo.path), media_type=photo.mime_type)
