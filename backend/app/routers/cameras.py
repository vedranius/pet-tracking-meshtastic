import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlmodel import select

from ..auth import require_login
from ..db import get_session
from ..models import Camera, CameraPreset, Setting, User
from ..schemas import CameraIn, PtzDefaultIn, PtzIdleReturnIn, PtzMoveIn, PtzPresetIn
from ..services import mediamtx_admin, ptz

log = logging.getLogger("pawtrack.cameras")

router = APIRouter(prefix="/api/cameras", tags=["cameras"], dependencies=[Depends(require_login)])

# mediamtx runs locally (see deploy/mediamtx.yml) and pulls each camera's RTSP
# feed on demand, remuxing it to HLS. We proxy its HTTP output through this
# authenticated route rather than exposing mediamtx's HLS port directly, so
# camera access goes through the same login session as the rest of the app.
MEDIAMTX_HLS_BASE = "http://127.0.0.1:8888"

# Idle-return timing is in-memory (per-process — fine, there's one app
# process); the idle timeout and default preset themselves are persisted in
# Setting so they survive a restart.
_last_ptz_command: dict[int, datetime] = {}
_returned_to_default: set[int] = set()


def _get_setting(session, key: str) -> str | None:
    row = session.get(Setting, key)
    return row.value if row and row.value else None


def _set_setting(session, key: str, value: str) -> None:
    row = session.get(Setting, key)
    if row:
        row.value = value
    else:
        row = Setting(key=key, value=value)
    session.add(row)


def _get_idle_minutes(session, cam_id: int) -> int | None:
    raw = _get_setting(session, f"cam:{cam_id}:ptz_idle_minutes")
    return int(raw) if raw else None


def _get_default_preset(session, cam_id: int) -> int | None:
    raw = _get_setting(session, f"cam:{cam_id}:ptz_default_preset_id")
    return int(raw) if raw else None


def _own_camera(session, camera_id: int, owner_id: int) -> Camera:
    cam = session.get(Camera, camera_id)
    if not cam or cam.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="not_found")
    return cam


def _require_ptz(cam: Camera) -> Camera:
    if not cam.is_ptz or not cam.ptz_host or not cam.ptz_user or not cam.ptz_password:
        raise HTTPException(status_code=400, detail="ptz_not_configured")
    return cam


@router.get("")
def list_cameras(user: User = Depends(require_login)):
    with get_session() as session:
        cams = session.exec(select(Camera).where(Camera.owner_id == user.id)).all()
        return [{"id": c.id, "name": c.name, "ptz": c.is_ptz} for c in cams]


@router.post("")
async def create_camera(payload: CameraIn, user: User = Depends(require_login)):
    with get_session() as session:
        cam = Camera(owner_id=user.id, **payload.model_dump())
        session.add(cam)
        session.commit()
        session.refresh(cam)
    await mediamtx_admin.sync_path(cam.id, cam.rtsp_url)
    return cam


@router.get("/{camera_id}/full")
def get_camera_full(camera_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        return _own_camera(session, camera_id, user.id)


@router.put("/{camera_id}")
async def update_camera(camera_id: int, payload: CameraIn, user: User = Depends(require_login)):
    with get_session() as session:
        cam = _own_camera(session, camera_id, user.id)
        for k, v in payload.model_dump().items():
            setattr(cam, k, v)
        session.add(cam)
        session.commit()
        session.refresh(cam)
    await mediamtx_admin.sync_path(cam.id, cam.rtsp_url)
    await ptz.close_handle(str(camera_id))
    return cam


@router.delete("/{camera_id}")
async def delete_camera(camera_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        cam = _own_camera(session, camera_id, user.id)
        for preset in session.exec(select(CameraPreset).where(CameraPreset.camera_id == camera_id)).all():
            session.delete(preset)
        _set_setting(session, f"cam:{camera_id}:ptz_idle_minutes", "")
        _set_setting(session, f"cam:{camera_id}:ptz_default_preset_id", "")
        session.delete(cam)
        session.commit()
    await mediamtx_admin.remove_path(camera_id)
    await ptz.close_handle(str(camera_id))
    _last_ptz_command.pop(camera_id, None)
    _returned_to_default.discard(camera_id)
    return {"ok": True}


@router.get("/{cam_id}/hls/{path:path}")
async def hls_proxy(cam_id: int, path: str, request: Request, user: User = Depends(require_login)):
    with get_session() as session:
        _own_camera(session, cam_id, user.id)
    url = f"{MEDIAMTX_HLS_BASE}/cam{cam_id}/{path}"
    # mediamtx's manifests embed a "?session=..." query param on every
    # sub-playlist/segment URL (its cookie-check fallback for plain HTTP —
    # see http_server.go) and expects it echoed back on the follow-up
    # requests. Drop it and every request after the first looks like a
    # fresh, unauthenticated session to mediamtx -> 401.
    if request.url.query:
        url += f"?{request.url.query}"
    try:
        # mediamtx pulls the camera on demand and can take a few seconds to
        # start (sourceOnDemandStartTimeout: 15s in mediamtx.yml) before it
        # answers the first playlist request — give it more room than that.
        # follow_redirects: mediamtx's HLS server 302s every fresh request
        # once (its "cookieCheck" anti-hotlink check, query-param based since
        # we talk to it over plain HTTP) before actually serving content.
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(url)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"stream_unreachable: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail="stream_unavailable")
    media_type = r.headers.get("content-type", "application/octet-stream")
    return Response(content=r.content, media_type=media_type, headers={"Cache-Control": "no-store"})


# -- PTZ ------------------------------------------------------------------

# Safety net for press-and-hold controls: if the frontend's move-stop never
# arrives (dropped request, closed tab, tunnel hiccup), stop the motor on
# our own after this long instead of letting it run into its end-stop.
MAX_HOLD_S = 8

_safety_tasks: dict[int, asyncio.Task] = {}


def _get_ptz_handle(cam: Camera) -> ptz._CameraHandle:
    return ptz.get_handle(str(cam.id), cam.ptz_host, cam.ptz_user, cam.ptz_password)


def _arm_safety_stop(camera_id: int, handle: ptz._CameraHandle) -> None:
    old = _safety_tasks.get(camera_id)
    if old and not old.done():
        old.cancel()

    async def _watchdog():
        try:
            await asyncio.sleep(MAX_HOLD_S)
            await handle.stop()
            log.warning("camera %s: safety stop fired (move-stop never arrived)", camera_id)
        except asyncio.CancelledError:
            pass
        except ptz.PtzError:
            log.exception("camera %s: safety stop failed", camera_id)

    _safety_tasks[camera_id] = asyncio.create_task(_watchdog())


def _disarm_safety_stop(camera_id: int) -> None:
    task = _safety_tasks.pop(camera_id, None)
    if task and not task.done():
        task.cancel()


@router.get("/{cam_id}/ptz")
def get_ptz_config(cam_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        cam = _own_camera(session, cam_id, user.id)
        _require_ptz(cam)
        presets = session.exec(
            select(CameraPreset).where(CameraPreset.camera_id == cam_id).order_by(CameraPreset.created_at)
        ).all()
        return {
            "presets": presets,
            "default_preset_id": _get_default_preset(session, cam_id),
            "idle_minutes": _get_idle_minutes(session, cam_id),
        }


@router.post("/{cam_id}/ptz/move-start")
async def ptz_move_start(cam_id: int, payload: PtzMoveIn, user: User = Depends(require_login)):
    with get_session() as session:
        cam = _own_camera(session, cam_id, user.id)
        _require_ptz(cam)
    handle = _get_ptz_handle(cam)
    try:
        await handle.continuous_move(payload.direction)
    except ptz.PtzError as e:
        raise HTTPException(status_code=502, detail=str(e))
    _arm_safety_stop(cam_id, handle)
    _last_ptz_command[cam_id] = datetime.now(timezone.utc)
    _returned_to_default.discard(cam_id)
    return {"ok": True}


@router.post("/{cam_id}/ptz/move-stop")
async def ptz_move_stop(cam_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        cam = _own_camera(session, cam_id, user.id)
        _require_ptz(cam)
    handle = _get_ptz_handle(cam)
    _disarm_safety_stop(cam_id)
    try:
        await handle.stop()
    except ptz.PtzError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True}


@router.post("/{cam_id}/ptz/presets")
async def create_preset(cam_id: int, payload: PtzPresetIn, user: User = Depends(require_login)):
    with get_session() as session:
        cam = _own_camera(session, cam_id, user.id)
        _require_ptz(cam)
    handle = _get_ptz_handle(cam)
    try:
        preset_token = await handle.set_preset(payload.name)
    except ptz.PtzError as e:
        raise HTTPException(status_code=502, detail=str(e))
    with get_session() as session:
        preset = CameraPreset(camera_id=cam_id, name=payload.name, preset_token=preset_token)
        session.add(preset)
        session.commit()
        session.refresh(preset)
        return preset


@router.delete("/{cam_id}/ptz/presets/{preset_id}")
async def delete_preset(cam_id: int, preset_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        cam = _own_camera(session, cam_id, user.id)
        _require_ptz(cam)
        preset = session.get(CameraPreset, preset_id)
        if not preset or preset.camera_id != cam_id:
            raise HTTPException(status_code=404, detail="not_found")
        handle = _get_ptz_handle(cam)
        try:
            await handle.remove_preset(preset.preset_token)
        except ptz.PtzError:
            pass  # best-effort — still drop our record even if the on-camera clear fails
        if _get_default_preset(session, cam_id) == preset_id:
            _set_setting(session, f"cam:{cam_id}:ptz_default_preset_id", "")
        session.delete(preset)
        session.commit()
    return {"ok": True}


@router.post("/{cam_id}/ptz/presets/{preset_id}/goto")
async def goto_preset_route(cam_id: int, preset_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        cam = _own_camera(session, cam_id, user.id)
        _require_ptz(cam)
        preset = session.get(CameraPreset, preset_id)
        if not preset or preset.camera_id != cam_id:
            raise HTTPException(status_code=404, detail="not_found")
    handle = _get_ptz_handle(cam)
    try:
        await handle.goto_preset(preset.preset_token)
    except ptz.PtzError as e:
        raise HTTPException(status_code=502, detail=str(e))
    _last_ptz_command[cam_id] = datetime.now(timezone.utc)
    _returned_to_default.discard(cam_id)
    return {"ok": True}


@router.put("/{cam_id}/ptz/default")
def set_default_preset(cam_id: int, payload: PtzDefaultIn, user: User = Depends(require_login)):
    with get_session() as session:
        cam = _own_camera(session, cam_id, user.id)
        _require_ptz(cam)
        if payload.preset_id is not None:
            preset = session.get(CameraPreset, payload.preset_id)
            if not preset or preset.camera_id != cam_id:
                raise HTTPException(status_code=404, detail="not_found")
            _set_setting(session, f"cam:{cam_id}:ptz_default_preset_id", str(payload.preset_id))
        else:
            _set_setting(session, f"cam:{cam_id}:ptz_default_preset_id", "")
        session.commit()
    _returned_to_default.discard(cam_id)
    return {"ok": True}


@router.put("/{cam_id}/ptz/idle-return")
def set_idle_return(cam_id: int, payload: PtzIdleReturnIn, user: User = Depends(require_login)):
    with get_session() as session:
        cam = _own_camera(session, cam_id, user.id)
        _require_ptz(cam)
        _set_setting(session, f"cam:{cam_id}:ptz_idle_minutes", str(payload.minutes) if payload.minutes else "")
        session.commit()
    _returned_to_default.discard(cam_id)
    return {"ok": True}


async def ptz_idle_watch() -> None:
    """Called periodically (see main.py) — sends any PTZ camera that has an
    idle-return timeout and a default preset configured back to that preset
    once it's been untouched for long enough."""
    with get_session() as session:
        cams = session.exec(select(Camera).where(Camera.is_ptz == True)).all()  # noqa: E712
        for cam in cams:
            if cam.id in _returned_to_default:
                continue
            last_cmd = _last_ptz_command.get(cam.id)
            if last_cmd is None:
                continue
            minutes = _get_idle_minutes(session, cam.id)
            if not minutes or minutes <= 0:
                continue
            preset_id = _get_default_preset(session, cam.id)
            if not preset_id:
                continue
            preset = session.get(CameraPreset, preset_id)
            if not preset:
                continue
            if datetime.now(timezone.utc) - last_cmd < timedelta(minutes=minutes):
                continue
            handle = _get_ptz_handle(cam)
            try:
                await handle.goto_preset(preset.preset_token)
                log.info("camera %s: auto-returned to default preset '%s'", cam.id, preset.name)
            except ptz.PtzError:
                log.warning("camera %s: auto-return to default preset failed", cam.id)
                continue
            _returned_to_default.add(cam.id)
