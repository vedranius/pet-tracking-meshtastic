from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    role: str = "user"  # "admin" | "user" — the first registered user becomes admin
    language: str = "hr"  # "hr" | "en" — used to render Telegram alert text server-side
    bio: Optional[str] = None
    avatar_path: Optional[str] = None  # relative path under <data>/uploads/avatars/
    avatar_mime: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Gateway(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    name: str
    ip_address: str = Field(index=True)
    enabled: bool = True
    is_admin_capable: bool = True
    status: str = "unknown"  # connected | disconnected | error
    last_seen: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Channel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(index=True)
    device_index: int = 1  # channel slot index on the radios (0 = primary/LongFast)
    psk_base64: Optional[str] = None
    position_precision: int = 32
    is_primary: bool = False
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Tracker(SQLModel, table=True):
    """A tracked pet + the Meshtastic node assigned to it. Kept as one entity
    rather than splitting "pet" and "tracker" into two tables — node_id is
    optional, so a pet can be added before a node is assigned to it, which
    covers the same workflow without an extra join."""
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    node_id: Optional[str] = Field(default=None, index=True)  # "!xxxxxxxx"
    name: str  # pet's name
    species: Optional[str] = None  # dog | cat | other — free text, UI-driven
    long_name: Optional[str] = None
    hw_model: Optional[str] = None
    color: str = "#2f7d5f"
    icon: str = "paw"
    channel_id: Optional[int] = Field(default=None, foreign_key="channel.id")
    active: bool = True
    battery_alert_threshold: int = 20
    offline_alert_minutes: int = 60
    last_lat: Optional[float] = None
    last_lon: Optional[float] = None
    last_alt: Optional[float] = None
    last_speed: Optional[float] = None
    last_battery: Optional[int] = None
    last_voltage: Optional[float] = None
    last_position_at: Optional[datetime] = None
    last_telemetry_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class Geofence(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    tracker_id: int = Field(foreign_key="tracker.id", index=True)
    name: str
    shape: str  # "circle" | "polygon"
    # circle: {"lat":..,"lon":..,"radius_m":..}
    # polygon: {"points":[[lat,lon], ...]}
    geometry_json: str
    enabled: bool = True
    is_inside: Optional[bool] = None  # last known state, for edge-triggering
    created_at: datetime = Field(default_factory=utcnow)


class Position(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tracker_id: int = Field(foreign_key="tracker.id", index=True)
    lat: float
    lon: float
    altitude: Optional[float] = None
    speed: Optional[float] = None
    sats: Optional[int] = None
    gateway_id: Optional[int] = Field(default=None, foreign_key="gateway.id")
    ts: datetime = Field(default_factory=utcnow, index=True)


class Telemetry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tracker_id: int = Field(foreign_key="tracker.id", index=True)
    battery_level: Optional[int] = None
    voltage: Optional[float] = None
    ts: datetime = Field(default_factory=utcnow, index=True)


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    tracker_id: Optional[int] = Field(default=None, foreign_key="tracker.id", index=True)
    type: str  # geofence_enter | geofence_exit | low_battery | offline | ring_sent
    message: str
    ts: datetime = Field(default_factory=utcnow, index=True)
    acknowledged: bool = False


class Setting(SQLModel, table=True):
    """Per-user settings (Telegram token/chat id, etc). key is namespaced as
    "<user_id>:<name>" so each account keeps its own Telegram/notification
    config."""
    key: str = Field(primary_key=True)
    value: str = ""


class Camera(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    name: str
    rtsp_url: str
    is_ptz: bool = False
    ptz_host: Optional[str] = None
    ptz_user: Optional[str] = None
    ptz_password: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class CameraPreset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    camera_id: int = Field(foreign_key="camera.id", index=True)
    name: str
    preset_token: str  # ONVIF PTZ preset token, as returned by SetPreset
    created_at: datetime = Field(default_factory=utcnow)


class DeviceLocation(SQLModel, table=True):
    """Live GPS location reported by a user's own phone (the Android
    companion app), used so an admin can see how far a pet is from the
    person sharing location with them."""
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    lat: float
    lon: float
    accuracy: Optional[float] = None
    battery: Optional[int] = None
    ts: datetime = Field(default_factory=utcnow, index=True)


class PetPhoto(SQLModel, table=True):
    """Photos of a pet (ideally from a few angles) — visible to every
    signed-in user, not just the owner or admin, since the whole point is
    helping someone recognize the animal if it's ever found by a stranger
    or reported by a neighbor."""
    id: Optional[int] = Field(default=None, primary_key=True)
    tracker_id: int = Field(foreign_key="tracker.id", index=True)
    path: str  # relative path under <data>/uploads/pets/<tracker_id>/
    mime_type: str
    created_at: datetime = Field(default_factory=utcnow)
