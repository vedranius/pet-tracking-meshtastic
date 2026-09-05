"""ONVIF PTZ control for cam1/cam2.

Confirmed against the real hardware (XM/Sofia-family cameras running the
"ICSee" vendor app, which itself offers ONVIF as an alternate control
path): both cameras expose a working ONVIF PTZ service on TCP/8899 with
the same admin credentials used for RTSP. The vendor's own DVRIP protocol
(OPPTZControl) also accepted commands cleanly but produced no physical
movement on either camera in testing — ONVIF ContinuousMove does.

A camera's ONVIFCamera/PTZ-service objects are cached per camera_id and
reused across calls: setting one up (xaddrs, WSDL, GetProfiles) has real
latency, and press-and-hold controls need to feel responsive.
"""
from __future__ import annotations

import asyncio
import logging

from onvif import ONVIFCamera

log = logging.getLogger("pawtrack.ptz")

ONVIF_PORT = 8899

# (x, y) pan/tilt velocity — magnitude tuned for a visible, controllable
# nudge; sign is what actually maps "up" to tilting up on this hardware.
DIRECTIONS = {
    "up": (0.0, 0.6),
    "down": (0.0, -0.6),
    "left": (-0.6, 0.0),
    "right": (0.6, 0.0),
}


class PtzError(Exception):
    pass


class _CameraHandle:
    def __init__(self, host: str, user: str, password: str):
        self.host, self.user, self.password = host, user, password
        self.cam: ONVIFCamera | None = None
        self.ptz_service = None
        self.profile_token: str | None = None
        self._lock = asyncio.Lock()

    async def _ensure_ready(self) -> None:
        if self.ptz_service is not None:
            return
        async with self._lock:
            if self.ptz_service is not None:
                return
            # no_cache: zeep's default WSDL cache writes to the service
            # user's home dir, which the systemd unit blocks (ProtectHome=
            # true) — avoid it rather than loosen that sandboxing. We only
            # pay the parse cost once per camera per process anyway, since
            # this handle is cached and reused.
            cam = ONVIFCamera(self.host, ONVIF_PORT, self.user, self.password, no_cache=True)
            try:
                await cam.update_xaddrs()
                media = await cam.create_media_service()
                profiles = await media.GetProfiles()
                if not profiles:
                    raise PtzError("kamera nema nijedan ONVIF profil")
                ptz_service = await cam.create_ptz_service()
            except PtzError:
                await cam.close()
                raise
            except Exception as e:
                await cam.close()
                raise PtzError(f"spajanje na kameru nije uspjelo: {e}") from e
            self.cam = cam
            self.ptz_service = ptz_service
            self.profile_token = profiles[0].token

    async def continuous_move(self, direction: str) -> None:
        if direction not in DIRECTIONS:
            raise PtzError(f"nepoznat smjer: {direction}")
        await self._ensure_ready()
        x, y = DIRECTIONS[direction]
        try:
            await self.ptz_service.ContinuousMove({
                "ProfileToken": self.profile_token,
                "Velocity": {"PanTilt": {"x": x, "y": y}},
            })
        except Exception as e:
            raise PtzError(f"PTZ naredba nije uspjela: {e}") from e

    async def stop(self) -> None:
        await self._ensure_ready()
        try:
            await self.ptz_service.Stop({"ProfileToken": self.profile_token, "PanTilt": True, "Zoom": False})
        except Exception as e:
            raise PtzError(f"zaustavljanje nije uspjelo: {e}") from e

    async def set_preset(self, name: str) -> str:
        await self._ensure_ready()
        try:
            token = await self.ptz_service.SetPreset({"ProfileToken": self.profile_token, "PresetName": name})
        except Exception as e:
            raise PtzError(f"spremanje pozicije nije uspjelo: {e}") from e
        return str(token)

    async def goto_preset(self, preset_token: str) -> None:
        await self._ensure_ready()
        try:
            await self.ptz_service.GotoPreset({"ProfileToken": self.profile_token, "PresetToken": preset_token})
        except Exception as e:
            raise PtzError(f"pomicanje na poziciju nije uspjelo: {e}") from e

    async def remove_preset(self, preset_token: str) -> None:
        await self._ensure_ready()
        try:
            await self.ptz_service.RemovePreset({"ProfileToken": self.profile_token, "PresetToken": preset_token})
        except Exception as e:
            raise PtzError(f"brisanje pozicije nije uspjelo: {e}") from e

    async def close(self) -> None:
        if self.cam is not None:
            await self.cam.close()


_handles: dict[str, _CameraHandle] = {}


def get_handle(cam_id: str, host: str, user: str, password: str) -> _CameraHandle:
    existing = _handles.get(cam_id)
    if existing and (existing.host, existing.user, existing.password) != (host, user, password):
        # credentials/host changed (camera edited) — drop the stale handle
        # rather than keep talking to the old address.
        _handles.pop(cam_id, None)
        existing = None
    if existing is None:
        _handles[cam_id] = _CameraHandle(host, user, password)
    return _handles[cam_id]


async def close_handle(cam_id: str) -> None:
    handle = _handles.pop(cam_id, None)
    if handle is not None:
        try:
            await handle.close()
        except Exception:
            log.exception("error closing ptz handle %s", cam_id)


async def close_all() -> None:
    for h in _handles.values():
        try:
            await h.close()
        except Exception:
            log.exception("error closing ptz handle")
    _handles.clear()
