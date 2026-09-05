"""Keeps mediamtx's path config in sync with the Camera table via its
control API, so adding/editing/removing a camera in the UI takes effect
immediately — no manual mediamtx.yml editing or restart.

Requires `api: yes` / `apiAddress: 127.0.0.1:9997` in mediamtx.yml (see
deploy/mediamtx.yml.example). If mediamtx isn't running or the API call
fails, we log and continue — camera CRUD in our own DB still succeeds, the
stream just won't come up until mediamtx is reachable again.
"""
import logging

import httpx

log = logging.getLogger("pawtrack.mediamtx")

MEDIAMTX_API_BASE = "http://127.0.0.1:9997"


def _path_name(camera_id: int) -> str:
    return f"cam{camera_id}"


async def sync_path(camera_id: int, rtsp_url: str) -> None:
    name = _path_name(camera_id)
    body = {
        "source": rtsp_url,
        "sourceOnDemand": True,
        "sourceOnDemandStartTimeout": "15s",
        "sourceOnDemandCloseAfter": "30s",
        "rtspTransport": "tcp",
    }
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.post(f"{MEDIAMTX_API_BASE}/v3/config/paths/add/{name}", json=body)
            if r.status_code == 400:
                # already exists — patch instead
                r = await client.patch(f"{MEDIAMTX_API_BASE}/v3/config/paths/patch/{name}", json=body)
            r.raise_for_status()
        except httpx.RequestError as e:
            log.warning("mediamtx not reachable while syncing camera %s: %s", camera_id, e)
        except httpx.HTTPStatusError as e:
            log.warning("mediamtx rejected path config for camera %s: %s", camera_id, e)


async def remove_path(camera_id: int) -> None:
    name = _path_name(camera_id)
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            r = await client.delete(f"{MEDIAMTX_API_BASE}/v3/config/paths/delete/{name}")
            if r.status_code not in (200, 404):
                r.raise_for_status()
        except httpx.RequestError as e:
            log.warning("mediamtx not reachable while removing camera %s: %s", camera_id, e)
        except httpx.HTTPStatusError as e:
            log.warning("mediamtx rejected removing camera %s: %s", camera_id, e)
