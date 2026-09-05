from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from ..auth import require_admin
from ..db import get_session
from ..models import (
    Camera,
    CameraPreset,
    Channel,
    DeviceLocation,
    Event,
    Gateway,
    Geofence,
    Position,
    Setting,
    Telemetry,
    Tracker,
    User,
)
from ..services.geo import haversine_m

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/users")
def list_users():
    with get_session() as session:
        users = session.exec(select(User).order_by(User.created_at)).all()
        return [{"id": u.id, "username": u.username, "role": u.role, "created_at": u.created_at} for u in users]


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="cannot_delete_self")
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="not_found")

        tracker_ids = [t.id for t in session.exec(select(Tracker).where(Tracker.owner_id == user_id)).all()]
        for model, col in [(Position, "tracker_id"), (Telemetry, "tracker_id")]:
            if tracker_ids:
                for row in session.exec(select(model).where(getattr(model, col).in_(tracker_ids))).all():
                    session.delete(row)

        camera_ids = [c.id for c in session.exec(select(Camera).where(Camera.owner_id == user_id)).all()]
        if camera_ids:
            for preset in session.exec(select(CameraPreset).where(CameraPreset.camera_id.in_(camera_ids))).all():
                session.delete(preset)

        for model in (Geofence, Tracker, Channel, Gateway, Camera, Event, DeviceLocation):
            for row in session.exec(select(model).where(model.owner_id == user_id)).all():
                session.delete(row)

        for row in session.exec(select(Setting).where(Setting.key.like(f"{user_id}:%"))).all():
            session.delete(row)

        session.delete(user)
        session.commit()
    return {"ok": True}


@router.get("/overview")
def overview(admin: User = Depends(require_admin)):
    with get_session() as session:
        users = session.exec(select(User)).all()
        admin_location = session.exec(
            select(DeviceLocation).where(DeviceLocation.owner_id == admin.id).order_by(DeviceLocation.ts.desc())
        ).first()

        result = []
        for u in users:
            trackers = session.exec(select(Tracker).where(Tracker.owner_id == u.id)).all()
            device_loc = session.exec(
                select(DeviceLocation).where(DeviceLocation.owner_id == u.id).order_by(DeviceLocation.ts.desc())
            ).first()

            distance_from_admin_m = None
            if admin_location and device_loc:
                distance_from_admin_m = haversine_m(
                    admin_location.lat, admin_location.lon, device_loc.lat, device_loc.lon
                )

            tracker_rows = []
            for t in trackers:
                dist = None
                if device_loc and t.last_lat is not None and t.last_lon is not None:
                    dist = haversine_m(device_loc.lat, device_loc.lon, t.last_lat, t.last_lon)
                elif admin_location and t.last_lat is not None and t.last_lon is not None:
                    dist = haversine_m(admin_location.lat, admin_location.lon, t.last_lat, t.last_lon)
                tracker_rows.append({
                    "id": t.id,
                    "name": t.name,
                    "color": t.color,
                    "active": t.active,
                    "last_lat": t.last_lat,
                    "last_lon": t.last_lon,
                    "last_battery": t.last_battery,
                    "last_position_at": t.last_position_at,
                    "distance_from_owner_m": dist,
                })

            result.append({
                "user": {"id": u.id, "username": u.username, "role": u.role},
                "device_location": device_loc,
                "distance_from_admin_m": distance_from_admin_m,
                "trackers": tracker_rows,
            })
        return {"admin_location": admin_location, "users": result}
