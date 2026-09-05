import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select

from ..auth import require_login
from ..db import get_session
from ..models import Geofence, Tracker, User
from ..schemas import GeofenceIn

router = APIRouter(prefix="/api/geofences", tags=["geofences"])


@router.get("")
def list_geofences(tracker_id: int | None = Query(default=None), user: User = Depends(require_login)):
    with get_session() as session:
        stmt = select(Geofence).where(Geofence.owner_id == user.id)
        if tracker_id is not None:
            stmt = stmt.where(Geofence.tracker_id == tracker_id)
        return session.exec(stmt).all()


@router.post("")
def create_geofence(payload: GeofenceIn, user: User = Depends(require_login)):
    with get_session() as session:
        tracker = session.get(Tracker, payload.tracker_id)
        if not tracker or tracker.owner_id != user.id:
            raise HTTPException(status_code=404, detail="tracker_not_found")
        g = Geofence(
            owner_id=user.id,
            tracker_id=payload.tracker_id,
            name=payload.name,
            shape=payload.shape,
            geometry_json=json.dumps(payload.geometry),
            enabled=payload.enabled,
        )
        session.add(g)
        session.commit()
        session.refresh(g)
        return g


@router.put("/{geofence_id}")
def update_geofence(geofence_id: int, payload: GeofenceIn, user: User = Depends(require_login)):
    with get_session() as session:
        g = session.get(Geofence, geofence_id)
        if not g or g.owner_id != user.id:
            raise HTTPException(status_code=404, detail="not_found")
        g.name = payload.name
        g.shape = payload.shape
        g.geometry_json = json.dumps(payload.geometry)
        g.enabled = payload.enabled
        g.is_inside = None  # re-baseline after edit
        session.add(g)
        session.commit()
        session.refresh(g)
        return g


@router.delete("/{geofence_id}")
def delete_geofence(geofence_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        g = session.get(Geofence, geofence_id)
        if not g or g.owner_id != user.id:
            raise HTTPException(status_code=404, detail="not_found")
        session.delete(g)
        session.commit()
    return {"ok": True}
