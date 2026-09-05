from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from ..auth import hash_password, register_user, require_admin, validate_password
from ..db import get_session
from ..models import (
    Camera,
    CameraPreset,
    Channel,
    DeviceLocation,
    Event,
    Gateway,
    Geofence,
    PetPhoto,
    Position,
    Setting,
    Telemetry,
    Tracker,
    User,
)
from ..schemas import RegisterIn
from ..services.geo import haversine_m
from ..services.uploads import delete_image

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class RoleIn(BaseModel):
    role: str  # "admin" | "user"


class PasswordResetIn(BaseModel):
    password: str


@router.get("/users")
def list_users():
    with get_session() as session:
        users = session.exec(select(User).order_by(User.created_at)).all()
        return [
            {
                "id": u.id, "username": u.username, "role": u.role,
                "bio": u.bio, "has_avatar": bool(u.avatar_path),
                "created_at": u.created_at,
            }
            for u in users
        ]


@router.post("/users")
def create_user(payload: RegisterIn):
    # register_user() would make this the admin if it's the very first
    # account ever — fine here too, since an admin creating the first other
    # account is exactly that path in practice.
    user = register_user(payload.username.strip(), payload.password)
    return {"id": user.id, "username": user.username, "role": user.role}


@router.put("/users/{user_id}/role")
def set_user_role(user_id: int, payload: RoleIn, admin: User = Depends(require_admin)):
    if payload.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="invalid_role")
    if user_id == admin.id and payload.role != "admin":
        raise HTTPException(status_code=400, detail="cannot_demote_self")
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="not_found")
        user.role = payload.role
        session.add(user)
        session.commit()
    return {"ok": True}


@router.put("/users/{user_id}/password")
def reset_user_password(user_id: int, payload: PasswordResetIn):
    validate_password(payload.password)
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="not_found")
        user.password_hash = hash_password(payload.password)
        session.add(user)
        session.commit()
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="cannot_delete_self")
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="not_found")

        tracker_ids = [t.id for t in session.exec(select(Tracker).where(Tracker.owner_id == user_id)).all()]
        photo_paths: list[str] = []
        for model, col in [(Position, "tracker_id"), (Telemetry, "tracker_id")]:
            if tracker_ids:
                for row in session.exec(select(model).where(getattr(model, col).in_(tracker_ids))).all():
                    session.delete(row)
        if tracker_ids:
            for photo in session.exec(select(PetPhoto).where(PetPhoto.tracker_id.in_(tracker_ids))).all():
                photo_paths.append(photo.path)
                session.delete(photo)

        camera_ids = [c.id for c in session.exec(select(Camera).where(Camera.owner_id == user_id)).all()]
        if camera_ids:
            for preset in session.exec(select(CameraPreset).where(CameraPreset.camera_id.in_(camera_ids))).all():
                session.delete(preset)

        for model in (Geofence, Tracker, Channel, Gateway, Camera, Event, DeviceLocation):
            for row in session.exec(select(model).where(model.owner_id == user_id)).all():
                session.delete(row)

        for row in session.exec(select(Setting).where(Setting.key.like(f"{user_id}:%"))).all():
            session.delete(row)

        avatar_path = user.avatar_path
        session.delete(user)
        session.commit()

    delete_image(avatar_path)
    for path in photo_paths:
        delete_image(path)
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
            photo_counts = {
                t.id: len(session.exec(select(PetPhoto).where(PetPhoto.tracker_id == t.id)).all())
                for t in trackers
            }
            geofences_by_tracker: dict[int, list] = {}
            for t in trackers:
                geofences_by_tracker[t.id] = session.exec(
                    select(Geofence).where(Geofence.tracker_id == t.id)
                ).all()

            gateways = session.exec(select(Gateway).where(Gateway.owner_id == u.id)).all()
            gateway_rows = [
                {"id": g.id, "name": g.name, "ip_address": g.ip_address, "enabled": g.enabled, "status": g.status}
                for g in gateways
            ]

            cameras = session.exec(select(Camera).where(Camera.owner_id == u.id)).all()
            camera_rows = [{"id": c.id, "name": c.name, "is_ptz": c.is_ptz} for c in cameras]

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
                    "photo_count": photo_counts.get(t.id, 0),
                    "geofences": [
                        {"id": g.id, "name": g.name, "shape": g.shape, "enabled": g.enabled}
                        for g in geofences_by_tracker.get(t.id, [])
                    ],
                })

            result.append({
                "user": {
                    "id": u.id, "username": u.username, "role": u.role,
                    "bio": u.bio, "has_avatar": bool(u.avatar_path),
                },
                "device_location": device_loc,
                "distance_from_admin_m": distance_from_admin_m,
                "trackers": tracker_rows,
                "gateways": gateway_rows,
                "cameras": camera_rows,
            })
        return {"admin_location": admin_location, "users": result}
