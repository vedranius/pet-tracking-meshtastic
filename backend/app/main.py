import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .db import init_db
from .routers import (
    admin,
    auth,
    cameras,
    channels,
    community,
    device_location,
    events,
    gateways,
    geofences,
    profile,
    settings,
    trackers,
    ws,
)
from .services import ptz
from .services.mesh_manager import mesh_manager
from .version import APP_VERSION

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

SECRET_KEY = os.environ.get("PAWTRACK_SECRET_KEY", "dev-secret-change-me")
FRONTEND_DIR = os.environ.get(
    "PAWTRACK_FRONTEND_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend"),
)


async def _offline_watch_loop():
    while True:
        try:
            await mesh_manager.check_offline()
        except Exception:
            logging.getLogger("pawtrack.main").exception("offline check failed")
        await asyncio.sleep(60)


async def _ptz_idle_watch_loop():
    while True:
        try:
            await cameras.ptz_idle_watch()
        except Exception:
            logging.getLogger("pawtrack.main").exception("ptz idle check failed")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    mesh_manager.bind_loop(asyncio.get_running_loop())
    mesh_manager.load_from_db()
    task = asyncio.create_task(_offline_watch_loop())
    ptz_task = asyncio.create_task(_ptz_idle_watch_loop())
    yield
    task.cancel()
    ptz_task.cancel()
    mesh_manager.shutdown()
    await ptz.close_all()


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    """CDNs/reverse proxies in front of a self-hosted deploy (Cloudflare in
    particular) cache recognized static extensions (.js/.css/...) at the
    edge for hours by default — entirely server-side, so a browser's own
    cache (even a fresh incognito one) has no bearing on it at all. We never
    send a Cache-Control header ourselves, which is exactly the condition
    that lets a CDN apply its own default heuristic instead of asking us.
    Force revalidation on every request for anything that isn't the API so
    a real content change (i.e. every deploy) is never stuck behind a
    multi-hour edge cache."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith(("/api", "/ws")):
            response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="PawTrack", lifespan=lifespan)
app.add_middleware(NoCacheStaticMiddleware)
# A non-default cookie name matters here: browsers scope cookies by domain
# and path only, not by port, so a second app on the same host (e.g. an
# existing deployment on a different port) using Starlette's default
# "session" cookie name would silently overwrite this one's cookie and vice
# versa — whichever app last set it "wins" until the next login, causing
# random-looking 401s in the other app.
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="pawtrack_session",
    same_site="lax",
    max_age=60 * 60 * 24 * 30,
)

@app.get("/api/version")
def get_version():
    # Deliberately unauthenticated — the whole point is being able to check
    # this (e.g. against the page's own cached copy) without needing to log
    # in first, to tell whether you're actually looking at the latest deploy.
    return {"version": APP_VERSION}


app.include_router(auth.router)
app.include_router(gateways.router)
app.include_router(channels.router)
app.include_router(trackers.router)
app.include_router(geofences.router)
app.include_router(events.router)
app.include_router(settings.router)
app.include_router(cameras.router)
app.include_router(device_location.router)
app.include_router(admin.router)
app.include_router(profile.router)
app.include_router(community.router)
app.include_router(ws.router)

if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
