from typing import Optional

from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str
    password: str


class GatewayIn(BaseModel):
    name: str
    ip_address: str
    enabled: bool = True
    is_admin_capable: bool = True


class ChannelIn(BaseModel):
    name: str
    device_index: int = 1
    psk_base64: Optional[str] = None
    position_precision: int = 32
    is_primary: bool = False
    notes: Optional[str] = None


class ChannelPushIn(BaseModel):
    # each target is either "gateway:<id>" (push to that gateway's own local
    # config) or a raw node_id like "!a1b2c3d4" (push via mesh admin)
    targets: list[str]
    primary: bool = False


class TrackerIn(BaseModel):
    node_id: Optional[str] = None
    name: str
    species: Optional[str] = None
    long_name: Optional[str] = None
    hw_model: Optional[str] = None
    color: str = "#2f7d5f"
    icon: str = "paw"
    channel_id: Optional[int] = None
    active: bool = True
    battery_alert_threshold: int = 20
    offline_alert_minutes: int = 60


class PositionConfigIn(BaseModel):
    gps_update_interval: int = 30
    broadcast_secs: int = 900
    smart_min_distance: int = 30
    smart_min_interval: int = 30


class PowerConfigIn(BaseModel):
    is_power_saving: bool = False
    ls_secs: int = 300


class BuzzerConfigIn(BaseModel):
    buzzer_mode: int = 0  # meshtastic Config.DeviceConfig.BuzzerMode enum


class GeofenceIn(BaseModel):
    tracker_id: int
    name: str
    shape: str  # circle | polygon
    geometry: dict
    enabled: bool = True


class SettingsIn(BaseModel):
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


class RingIn(BaseModel):
    text: Optional[str] = None


class PtzMoveIn(BaseModel):
    direction: str  # up | down | left | right


class PtzPresetIn(BaseModel):
    name: str


class PtzDefaultIn(BaseModel):
    preset_id: Optional[int] = None


class PtzIdleReturnIn(BaseModel):
    minutes: Optional[int] = None


class CameraIn(BaseModel):
    name: str
    rtsp_url: str
    is_ptz: bool = False
    ptz_host: Optional[str] = None
    ptz_user: Optional[str] = None
    ptz_password: Optional[str] = None


class DeviceLocationIn(BaseModel):
    lat: float
    lon: float
    accuracy: Optional[float] = None
    battery: Optional[int] = None


class PasswordIn(BaseModel):
    password: str
