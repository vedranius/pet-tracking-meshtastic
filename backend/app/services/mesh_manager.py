from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from pubsub import pub
from sqlmodel import select

from ..db import get_session
from ..models import Event, Gateway, Geofence, Position, Telemetry, Tracker, User
from . import geo
from .telegram import send_telegram
from .ws_manager import ws_manager

log = logging.getLogger("pawtrack.mesh")

RECONNECT_BACKOFF = [2, 5, 10, 20, 30, 60]


class GatewayConnection:
    def __init__(self, manager: "MeshManager", gateway_id: int, ip_address: str):
        self.manager = manager
        self.gateway_id = gateway_id
        self.ip_address = ip_address
        self.interface = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self.interface is not None:
            try:
                self.interface.close()
            except Exception:
                pass

    def _run(self) -> None:
        from meshtastic.tcp_interface import TCPInterface

        pub.subscribe(self._on_receive, "meshtastic.receive")
        pub.subscribe(self._on_lost, "meshtastic.connection.lost")

        attempt = 0
        while not self._stop.is_set():
            try:
                log.info("gateway %s: connecting to %s", self.gateway_id, self.ip_address)
                self.interface = TCPInterface(hostname=self.ip_address)
                attempt = 0
                self.manager.set_status(self.gateway_id, "connected")
                # block this thread while the interface's own reader thread runs
                while not self._stop.is_set() and self.interface is not None:
                    time.sleep(1)
            except Exception as e:
                log.warning("gateway %s: connection error: %s", self.gateway_id, e)
                self.manager.set_status(self.gateway_id, "error", str(e))
                self.interface = None
            if self._stop.is_set():
                break
            delay = RECONNECT_BACKOFF[min(attempt, len(RECONNECT_BACKOFF) - 1)]
            attempt += 1
            time.sleep(delay)

    def _on_lost(self, interface=None):
        if interface is not self.interface:
            return
        log.warning("gateway %s: connection lost", self.gateway_id)
        self.manager.set_status(self.gateway_id, "disconnected")
        self.interface = None

    def _on_receive(self, packet=None, interface=None):
        if interface is not self.interface or packet is None:
            return
        self.manager.dispatch(self.gateway_id, packet)


class MeshManager:
    def __init__(self) -> None:
        self._connections: dict[int, GatewayConnection] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._battery_alerted: set[int] = set()
        self._offline_alerted: set[int] = set()
        self._fence_exit_streak: dict[int, int] = {}
        self._fence_last_update_sent: dict[int, datetime] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # -- lifecycle -----------------------------------------------------
    def load_from_db(self) -> None:
        with get_session() as session:
            gateways = session.exec(select(Gateway).where(Gateway.enabled == True)).all()  # noqa: E712
        for gw in gateways:
            self.add_gateway(gw.id, gw.ip_address)

    def add_gateway(self, gateway_id: int, ip_address: str) -> None:
        if gateway_id in self._connections:
            self.remove_gateway(gateway_id)
        conn = GatewayConnection(self, gateway_id, ip_address)
        self._connections[gateway_id] = conn
        conn.start()

    def remove_gateway(self, gateway_id: int) -> None:
        conn = self._connections.pop(gateway_id, None)
        if conn:
            conn.stop()

    def shutdown(self) -> None:
        for gid in list(self._connections):
            self.remove_gateway(gid)

    # -- status ----------------------------------------------------------
    def set_status(self, gateway_id: int, status: str, error: str | None = None) -> None:
        owner_id = None
        with get_session() as session:
            gw = session.get(Gateway, gateway_id)
            if not gw:
                return
            gw.status = status
            gw.last_error = error
            if status == "connected":
                gw.last_seen = datetime.now(timezone.utc)
            session.add(gw)
            session.commit()
            owner_id = gw.owner_id
        self._emit_owner({"type": "gateway_status", "gateway_id": gateway_id, "status": status, "error": error}, owner_id)

    def get_active_interface(self, gateway_ids: list[int] | None = None):
        for gid, conn in self._connections.items():
            if gateway_ids is not None and gid not in gateway_ids:
                continue
            if conn.interface is None:
                continue
            return conn.interface
        return None

    def get_interface_for_gateway(self, gateway_id: int):
        conn = self._connections.get(gateway_id)
        return conn.interface if conn else None

    def get_known_nodes(self, gateway_id: int) -> list[dict]:
        conn = self._connections.get(gateway_id)
        if not conn or conn.interface is None:
            return []
        out = []
        for node in conn.interface.nodes.values():
            user = node.get("user", {})
            out.append({
                "node_id": user.get("id"),
                "short_name": user.get("shortName"),
                "long_name": user.get("longName"),
                "hw_model": user.get("hwModel"),
            })
        return out

    # -- dispatch from worker thread -> asyncio loop ----------------------
    def dispatch(self, gateway_id: int, packet: dict) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._handle_packet(gateway_id, packet), self._loop)

    def _emit_owner(self, payload: dict, owner_id: int) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(ws_manager.broadcast_owner(payload, owner_id), self._loop)

    async def _handle_packet(self, gateway_id: int, packet: dict) -> None:
        try:
            from_id = packet.get("fromId")
            decoded = packet.get("decoded") or {}
            port = decoded.get("portnum")
            if not from_id or not port:
                return

            with get_session() as session:
                gateway = session.get(Gateway, gateway_id)
                if not gateway:
                    return
                # a tracker only belongs to whoever owns the gateway that
                # heard it — trackers and gateways are scoped to the same
                # account's mesh, never cross-account.
                tracker = session.exec(
                    select(Tracker).where(Tracker.node_id == from_id, Tracker.owner_id == gateway.owner_id)
                ).first()
                if not tracker or not tracker.active:
                    return

                if port == "POSITION_APP":
                    await self._handle_position(session, tracker, decoded.get("position", {}), gateway_id)
                elif port == "TELEMETRY_APP":
                    await self._handle_telemetry(session, tracker, decoded.get("telemetry", {}))
        except Exception:
            log.exception("error handling packet")

    async def _handle_position(self, session, tracker: Tracker, pos: dict, gateway_id: int) -> None:
        lat = pos.get("latitude")
        lon = pos.get("longitude")
        if lat is None or lon is None:
            return
        alt = pos.get("altitude")
        speed = pos.get("groundSpeed")
        sats = pos.get("satsInView")

        tracker.last_lat = lat
        tracker.last_lon = lon
        tracker.last_alt = alt
        tracker.last_speed = speed
        tracker.last_position_at = datetime.now(timezone.utc)
        session.add(tracker)

        record = Position(tracker_id=tracker.id, lat=lat, lon=lon, altitude=alt,
                           speed=speed, sats=sats, gateway_id=gateway_id)
        session.add(record)
        session.commit()
        session.refresh(tracker)

        self._offline_alerted.discard(tracker.id)

        await ws_manager.broadcast_owner({
            "type": "position",
            "tracker_id": tracker.id,
            "lat": lat, "lon": lon, "altitude": alt, "speed": speed,
            "ts": record.ts.isoformat(),
        }, tracker.owner_id)

        await self._evaluate_geofences(session, tracker, lat, lon)

    async def _handle_telemetry(self, session, tracker: Tracker, tele: dict) -> None:
        dm = tele.get("deviceMetrics", {})
        batt = dm.get("batteryLevel")
        volt = dm.get("voltage")
        if batt is None and volt is None:
            return

        tracker.last_battery = batt
        tracker.last_voltage = volt
        tracker.last_telemetry_at = datetime.now(timezone.utc)
        session.add(tracker)

        record = Telemetry(tracker_id=tracker.id, battery_level=batt, voltage=volt)
        session.add(record)
        session.commit()
        session.refresh(tracker)

        await ws_manager.broadcast_owner({
            "type": "telemetry",
            "tracker_id": tracker.id,
            "battery_level": batt, "voltage": volt,
            "ts": record.ts.isoformat(),
        }, tracker.owner_id)

        if batt is not None:
            if batt <= tracker.battery_alert_threshold and tracker.id not in self._battery_alerted:
                self._battery_alerted.add(tracker.id)
                msg = f"low_battery::{tracker.name}::{batt}"
                await self._raise_event(session, tracker, "low_battery", msg)
            elif batt > tracker.battery_alert_threshold + 5:
                self._battery_alerted.discard(tracker.id)

    # A single GPS fix landing outside a fence isn't reliable evidence of a
    # real exit — consumer GPS jitter (worse near/inside a house) routinely
    # exceeds the size of a yard-sized polygon, so raw in/out flips almost
    # every reading even when the tracker hasn't moved. Require this many
    # *consecutive* outside readings before confirming a real exit.
    FENCE_EXIT_STREAK = 2
    # Once confirmed outside, don't re-alert on every single subsequent fix
    # (some arrive seconds apart) — space repeat "still outside" pushes out.
    FENCE_UPDATE_THROTTLE = timedelta(minutes=3)

    async def _evaluate_geofences(self, session, tracker: Tracker, lat: float, lon: float) -> None:
        fences = session.exec(
            select(Geofence).where(Geofence.tracker_id == tracker.id, Geofence.enabled == True)  # noqa: E712
        ).all()
        now = datetime.now(timezone.utc)
        for fence in fences:
            raw_inside = geo.is_inside(fence.geometry_json, fence.shape, lat, lon)
            prev = fence.is_inside

            if prev is None:
                fence.is_inside = raw_inside
                session.add(fence)
                session.commit()
                continue  # first reading, just establish baseline

            if raw_inside:
                self._fence_exit_streak.pop(fence.id, None)
                if not prev:
                    fence.is_inside = True
                    session.add(fence)
                    session.commit()
                    msg = f"geofence_enter::{tracker.name}::{fence.name}"
                    await self._raise_event(session, tracker, "geofence_enter", msg)
                continue

            # raw_inside is False from here on
            if prev:
                streak = self._fence_exit_streak.get(fence.id, 0) + 1
                self._fence_exit_streak[fence.id] = streak
                if streak < self.FENCE_EXIT_STREAK:
                    continue  # could just be GPS jitter — not confirmed yet
                fence.is_inside = False
                session.add(fence)
                session.commit()
                self._fence_last_update_sent[fence.id] = now
                msg = f"geofence_exit::{tracker.name}::{fence.name}::{lat}::{lon}"
                await self._raise_event(session, tracker, "geofence_exit", msg)
            else:
                last_sent = self._fence_last_update_sent.get(fence.id)
                if last_sent and now - last_sent < self.FENCE_UPDATE_THROTTLE:
                    continue
                self._fence_last_update_sent[fence.id] = now
                msg = f"geofence_exit_update::{tracker.name}::{fence.name}::{lat}::{lon}"
                await self._raise_event(session, tracker, "geofence_exit_update", msg)

    async def _raise_event(self, session, tracker: Tracker, type_: str, message: str) -> None:
        event = Event(owner_id=tracker.owner_id, tracker_id=tracker.id, type=type_, message=message)
        session.add(event)
        session.commit()
        session.refresh(event)
        await ws_manager.broadcast_owner({
            "type": "alert",
            "event_type": type_,
            "tracker_id": tracker.id,
            "message": message,
            "ts": event.ts.isoformat(),
        }, tracker.owner_id)
        owner = session.get(User, tracker.owner_id)
        lang = owner.language if owner else "hr"
        await send_telegram(session, tracker.owner_id, render_event_text(type_, message, lang))

    # -- periodic offline check ------------------------------------------
    async def check_offline(self) -> None:
        with get_session() as session:
            trackers = session.exec(select(Tracker).where(Tracker.active == True)).all()  # noqa: E712
            now = datetime.now(timezone.utc)
            for t in trackers:
                if not t.last_position_at:
                    continue
                last_position_at = t.last_position_at
                if last_position_at.tzinfo is None:
                    # SQLite round-trips datetimes as naive; we always write UTC.
                    last_position_at = last_position_at.replace(tzinfo=timezone.utc)
                cutoff = last_position_at + timedelta(minutes=t.offline_alert_minutes)
                if now > cutoff and t.id not in self._offline_alerted:
                    self._offline_alerted.add(t.id)
                    msg = f"offline::{t.name}::{t.offline_alert_minutes}"
                    await self._raise_event(session, t, "offline", msg)


# Event.message is stored as a "::"-delimited template id + args (not the
# final human sentence) so it can be re-rendered in whichever language the
# viewer/owner has selected, rather than baking Croatian/English text into
# the DB at the moment the event happened. The frontend re-renders the same
# way from the same template ids for the Alerts view and toasts (see
# frontend/js/eventText.js) — keep both in sync.
_EVENT_TEMPLATES = {
    "hr": {
        "low_battery": "⚠️ {name} baterija: {battery}%",
        "geofence_enter": "✅ {name} se vratila u područje “{fence}”",
        "geofence_exit": "\U0001f6a8 {name} je izašla iz područja “{fence}”! https://maps.google.com/?q={lat},{lon}",
        "geofence_exit_update": "\U0001f4cd {name} je i dalje izvan područja “{fence}” https://maps.google.com/?q={lat},{lon}",
        "offline": "\U0001f4f4 {name} se ne javlja preko {minutes} min",
        "ring_sent": "\U0001f514 Poruka za zvonjavu poslana ({name})",
    },
    "en": {
        "low_battery": "⚠️ {name} battery: {battery}%",
        "geofence_enter": "✅ {name} is back inside “{fence}”",
        "geofence_exit": "\U0001f6a8 {name} left “{fence}”! https://maps.google.com/?q={lat},{lon}",
        "geofence_exit_update": "\U0001f4cd {name} is still outside “{fence}” https://maps.google.com/?q={lat},{lon}",
        "offline": "\U0001f4f4 {name} hasn't reported in for {minutes} min",
        "ring_sent": "\U0001f514 Ring command sent ({name})",
    },
}


def render_event_text(type_: str, message: str, lang: str = "hr") -> str:
    parts = message.split("::")
    tpl = _EVENT_TEMPLATES.get(lang, _EVENT_TEMPLATES["hr"]).get(type_)
    if not tpl:
        return message
    try:
        if type_ == "low_battery":
            return tpl.format(name=parts[1], battery=parts[2])
        if type_ == "geofence_enter":
            return tpl.format(name=parts[1], fence=parts[2])
        if type_ in ("geofence_exit", "geofence_exit_update"):
            return tpl.format(name=parts[1], fence=parts[2], lat=parts[3], lon=parts[4])
        if type_ == "offline":
            return tpl.format(name=parts[1], minutes=parts[2])
        if type_ == "ring_sent":
            return tpl.format(name=parts[1])
    except IndexError:
        return message
    return message


mesh_manager = MeshManager()
