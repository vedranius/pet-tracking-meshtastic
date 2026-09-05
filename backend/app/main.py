import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .db import init_db
from .routers import admin, auth, cameras, channels, device_location, events, gateways, geofences, settings, trackers, ws
from .services import ptz
from .services.mesh_manager import mesh_manager

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


app = FastAPI(title="PawTrack", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", max_age=60 * 60 * 24 * 30)

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
app.include_router(ws.router)

if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
