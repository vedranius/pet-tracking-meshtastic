from fastapi import APIRouter, Depends, HTTPException, Query
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
    TrackerCaretaker,
    User,
)
from ..schemas import RegisterIn
from ..services import mediamtx_admin
from ..services.geo import haversine_m
from ..services.timerange import resolve_range
from ..services.uploads import delete_image

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class RoleIn(BaseModel):
    role: str  # "admin" | "user"


class PasswordResetIn(BaseModel):
    password: str


class LocationSharingIn(BaseModel):
    enabled: bool


class CopySettingsIn(BaseModel):
    from_user_id: int
    to_user_id: int
    include_gateways: bool = True
    include_channels: bool = True
    include_pets: bool = True
    include_cameras: bool = True


class CaretakerIn(BaseModel):
    user_id: int


class MergeTrackersIn(BaseModel):
    primary_tracker_id: int
    duplicate_tracker_ids: list[int]


@router.get("/users")
def list_users():
    with get_session() as session:
        users = session.exec(select(User).order_by(User.created_at)).all()
        return [
            {
                "id": u.id, "username": u.username, "role": u.role,
                "bio": u.bio, "has_avatar": bool(u.avatar_path),
                "location_sharing_enabled": u.location_sharing_enabled,
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


@router.put("/users/{user_id}/location-sharing")
def set_location_sharing(user_id: int, payload: LocationSharingIn):
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="not_found")
        user.location_sharing_enabled = payload.enabled
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

        if tracker_ids:
            for row in session.exec(select(TrackerCaretaker).where(TrackerCaretaker.tracker_id.in_(tracker_ids))).all():
                session.delete(row)
        for row in session.exec(select(TrackerCaretaker).where(TrackerCaretaker.user_id == user_id)).all():
            session.delete(row)

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
        usernames = {u.id: u.username for u in users}
        admin_location = session.exec(
            select(DeviceLocation).where(DeviceLocation.owner_id == admin.id).order_by(DeviceLocation.ts.desc())
        ).first()
        caretakers_by_tracker: dict[int, list[int]] = {}
        for tc in session.exec(select(TrackerCaretaker)).all():
            caretakers_by_tracker.setdefault(tc.tracker_id, []).append(tc.user_id)

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
                    "caretakers": [
                        {"id": uid, "username": usernames.get(uid, "?")}
                        for uid in caretakers_by_tracker.get(t.id, [])
                    ],
                })

            result.append({
                "user": {
                    "id": u.id, "username": u.username, "role": u.role,
                    "bio": u.bio, "has_avatar": bool(u.avatar_path),
                    "location_sharing_enabled": u.location_sharing_enabled,
                },
                "device_location": device_loc,
                "distance_from_admin_m": distance_from_admin_m,
                "trackers": tracker_rows,
                "gateways": gateway_rows,
                "cameras": camera_rows,
            })
        return {"admin_location": admin_location, "users": result}


# -- history / timeline (any pet or user, not just the admin's own) --------

@router.get("/trackers/{tracker_id}/positions")
def admin_tracker_positions(
    tracker_id: int,
    hours: int = Query(default=24, le=24 * 30),
    date: str | None = Query(default=None, description="YYYY-MM-DD (UTC) — overrides `hours` to one specific day"),
):
    since, until = resolve_range(hours, date)
    with get_session() as session:
        if not session.get(Tracker, tracker_id):
            raise HTTPException(status_code=404, detail="not_found")
        stmt = select(Position).where(Position.tracker_id == tracker_id, Position.ts >= since)
        if until:
            stmt = stmt.where(Position.ts < until)
        return session.exec(stmt.order_by(Position.ts)).all()


@router.get("/users/{user_id}/device-locations")
def admin_device_locations(
    user_id: int,
    hours: int = Query(default=24, le=24 * 30),
    date: str | None = Query(default=None, description="YYYY-MM-DD (UTC) — overrides `hours` to one specific day"),
):
    since, until = resolve_range(hours, date)
    with get_session() as session:
        if not session.get(User, user_id):
            raise HTTPException(status_code=404, detail="not_found")
        stmt = select(DeviceLocation).where(DeviceLocation.owner_id == user_id, DeviceLocation.ts >= since)
        if until:
            stmt = stmt.where(DeviceLocation.ts < until)
        return session.exec(stmt.order_by(DeviceLocation.ts)).all()


# -- copy settings between accounts ----------------------------------------
# For households where several family members each want their own login
# (so the admin can see everyone's individual location) but share the same
# gateway nodes, pets, and cameras — saves re-entering IPs/PSKs/RTSP URLs by
# hand for every account. Deliberately *copies*, not shares: each account
# ends up with its own independent rows, no live data is duplicated, and a
# copied gateway is always disabled by default (Meshtastic's WiFi TCP API
# only accepts one connected client per node — enabling both the original
# and the copy at the same time reproduces the exact connection-contention
# bug this project already hit once).

@router.post("/copy-settings")
async def copy_settings(payload: CopySettingsIn):
    if payload.from_user_id == payload.to_user_id:
        raise HTTPException(status_code=400, detail="same_user")

    counts = {"gateways": 0, "channels": 0, "pets": 0, "geofences": 0, "cameras": 0}
    new_camera_ids: list[tuple[int, str]] = []

    with get_session() as session:
        from_user = session.get(User, payload.from_user_id)
        to_user = session.get(User, payload.to_user_id)
        if not from_user or not to_user:
            raise HTTPException(status_code=404, detail="not_found")

        channel_map: dict[int, int] = {}
        if payload.include_channels:
            for ch in session.exec(select(Channel).where(Channel.owner_id == from_user.id)).all():
                new_ch = Channel(
                    owner_id=to_user.id, name=ch.name, device_index=ch.device_index,
                    psk_base64=ch.psk_base64, position_precision=ch.position_precision,
                    is_primary=ch.is_primary, notes=ch.notes,
                )
                session.add(new_ch)
                session.flush()  # assigns new_ch.id without committing, so trackers below can reference it
                channel_map[ch.id] = new_ch.id
                counts["channels"] += 1

        if payload.include_gateways:
            for gw in session.exec(select(Gateway).where(Gateway.owner_id == from_user.id)).all():
                session.add(Gateway(
                    owner_id=to_user.id, name=gw.name, ip_address=gw.ip_address,
                    enabled=False,  # never auto-enable — see module docstring above
                    is_admin_capable=gw.is_admin_capable,
                ))
                counts["gateways"] += 1

        if payload.include_pets:
            for tr in session.exec(select(Tracker).where(Tracker.owner_id == from_user.id)).all():
                new_tr = Tracker(
                    owner_id=to_user.id, node_id=tr.node_id, name=tr.name, species=tr.species,
                    long_name=tr.long_name, hw_model=tr.hw_model, color=tr.color, icon=tr.icon,
                    channel_id=channel_map.get(tr.channel_id) if tr.channel_id else None,
                    active=tr.active, battery_alert_threshold=tr.battery_alert_threshold,
                    offline_alert_minutes=tr.offline_alert_minutes,
                )
                session.add(new_tr)
                session.flush()
                counts["pets"] += 1
                for g in session.exec(select(Geofence).where(Geofence.tracker_id == tr.id)).all():
                    session.add(Geofence(
                        owner_id=to_user.id, tracker_id=new_tr.id, name=g.name, shape=g.shape,
                        geometry_json=g.geometry_json, enabled=g.enabled,
                    ))
                    counts["geofences"] += 1

        if payload.include_cameras:
            for cam in session.exec(select(Camera).where(Camera.owner_id == from_user.id)).all():
                new_cam = Camera(
                    owner_id=to_user.id, name=cam.name, rtsp_url=cam.rtsp_url, is_ptz=cam.is_ptz,
                    ptz_host=cam.ptz_host, ptz_user=cam.ptz_user, ptz_password=cam.ptz_password,
                )
                session.add(new_cam)
                session.flush()
                new_camera_ids.append((new_cam.id, new_cam.rtsp_url))
                counts["cameras"] += 1

        session.commit()

    # Cameras (unlike gateways) support multiple simultaneous RTSP viewers,
    # so it's safe to wire the copy's mediamtx path up immediately.
    for cam_id, rtsp_url in new_camera_ids:
        await mediamtx_admin.sync_path(cam_id, rtsp_url)

    return {"ok": True, "copied": counts}


# -- caretakers (share one pet's live data with more than one account) -----
# The owner (Tracker.owner_id) keeps exclusive control — editing the pet,
# its geofences, and pushing radio config all stay owner/admin-only. A
# caretaker only gets read access: the pet shows up on their own Dashboard
# (live position, geofences, timeline) as if they were the owner.

@router.post("/trackers/{tracker_id}/caretakers")
def add_caretaker(tracker_id: int, payload: CaretakerIn):
    with get_session() as session:
        tracker = session.get(Tracker, tracker_id)
        if not tracker:
            raise HTTPException(status_code=404, detail="not_found")
        if not session.get(User, payload.user_id):
            raise HTTPException(status_code=404, detail="user_not_found")
        if payload.user_id == tracker.owner_id:
            raise HTTPException(status_code=400, detail="already_owner")
        existing = session.exec(
            select(TrackerCaretaker).where(
                TrackerCaretaker.tracker_id == tracker_id, TrackerCaretaker.user_id == payload.user_id
            )
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="already_caretaker")
        session.add(TrackerCaretaker(tracker_id=tracker_id, user_id=payload.user_id))
        session.commit()
    return {"ok": True}


@router.delete("/trackers/{tracker_id}/caretakers/{user_id}")
def remove_caretaker(tracker_id: int, user_id: int):
    with get_session() as session:
        row = session.exec(
            select(TrackerCaretaker).where(
                TrackerCaretaker.tracker_id == tracker_id, TrackerCaretaker.user_id == user_id
            )
        ).first()
        if not row:
            raise HTTPException(status_code=404, detail="not_found")
        session.delete(row)
        session.commit()
    return {"ok": True}


# -- merge duplicate pets ---------------------------------------------------
# Before caretakers existed, the only way to share a pet across accounts was
# Copy settings, which clones it as a second independent Tracker row — so a
# household using that ends up with the same pet listed once per account.
# This finds those look-alike groups and lets an admin fold them into one
# real Tracker with everyone else added as a caretaker instead.

@router.get("/duplicate-pets")
def duplicate_pets():
    with get_session() as session:
        trackers = session.exec(select(Tracker).order_by(Tracker.created_at)).all()
        usernames = {u.id: u.username for u in session.exec(select(User)).all()}
        photo_counts: dict[int, int] = {}
        for photo in session.exec(select(PetPhoto)).all():
            photo_counts[photo.tracker_id] = photo_counts.get(photo.tracker_id, 0) + 1

        groups: dict[tuple[str, str | None], list[Tracker]] = {}
        for t in trackers:
            key = (t.name.strip().lower(), t.species)
            groups.setdefault(key, []).append(t)

        return [
            {
                "key": f"{key[0]}|{key[1] or ''}",
                "trackers": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "species": t.species,
                        "owner_id": t.owner_id,
                        "owner_username": usernames.get(t.owner_id, "?"),
                        "photo_count": photo_counts.get(t.id, 0),
                        "last_position_at": t.last_position_at,
                        "created_at": t.created_at,
                    }
                    for t in members
                ],
            }
            for key, members in groups.items()
            if len(members) > 1
        ]


@router.post("/merge-trackers")
def merge_trackers(payload: MergeTrackersIn):
    if payload.primary_tracker_id in payload.duplicate_tracker_ids:
        raise HTTPException(status_code=400, detail="primary_in_duplicates")
    if not payload.duplicate_tracker_ids:
        raise HTTPException(status_code=400, detail="no_duplicates")

    with get_session() as session:
        primary = session.get(Tracker, payload.primary_tracker_id)
        if not primary:
            raise HTTPException(status_code=404, detail="primary_not_found")
        duplicates = session.exec(
            select(Tracker).where(Tracker.id.in_(payload.duplicate_tracker_ids))
        ).all()
        if len(duplicates) != len(payload.duplicate_tracker_ids):
            raise HTTPException(status_code=404, detail="duplicate_not_found")

        existing_caretakers = {
            tc.user_id
            for tc in session.exec(
                select(TrackerCaretaker).where(TrackerCaretaker.tracker_id == primary.id)
            ).all()
        }
        added_caretakers = 0
        photo_paths: list[str] = []

        for dup in duplicates:
            # the duplicate's own owner, and anyone already added as a
            # caretaker on it, both become caretakers on the surviving pet
            candidate_ids = {dup.owner_id} | {
                tc.user_id
                for tc in session.exec(
                    select(TrackerCaretaker).where(TrackerCaretaker.tracker_id == dup.id)
                ).all()
            }
            for uid in candidate_ids:
                if uid == primary.owner_id or uid in existing_caretakers:
                    continue
                session.add(TrackerCaretaker(tracker_id=primary.id, user_id=uid))
                existing_caretakers.add(uid)
                added_caretakers += 1

            for row in session.exec(select(TrackerCaretaker).where(TrackerCaretaker.tracker_id == dup.id)).all():
                session.delete(row)
            for row in session.exec(select(Position).where(Position.tracker_id == dup.id)).all():
                session.delete(row)
            for row in session.exec(select(Telemetry).where(Telemetry.tracker_id == dup.id)).all():
                session.delete(row)
            for row in session.exec(select(Geofence).where(Geofence.tracker_id == dup.id)).all():
                session.delete(row)
            for photo in session.exec(select(PetPhoto).where(PetPhoto.tracker_id == dup.id)).all():
                photo_paths.append(photo.path)
                session.delete(photo)
            for row in session.exec(select(Event).where(Event.tracker_id == dup.id)).all():
                session.delete(row)
            session.delete(dup)

        session.commit()

    for path in photo_paths:
        delete_image(path)

    return {"ok": True, "caretakers_added": added_caretakers, "merged": len(duplicates)}
