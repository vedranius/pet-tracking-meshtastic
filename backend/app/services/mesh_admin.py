"""Remote config helpers that ride on the mesh admin channel.

These talk to a *connected* meshtastic TCPInterface and push changes to a
remote node (gateway itself, or a tracker the gateway administers, like
Roxy) via Meshtastic's AdminMessage protocol. Admin round-trips go over
LoRa so they are slow (seconds) and can fail if the remote node is asleep
or out of range — callers should treat these as best-effort and report
failures back to the UI rather than assuming success.
"""
from __future__ import annotations

import base64
import logging
import os
import time

log = logging.getLogger("pawtrack.mesh_admin")

ADMIN_TIMEOUT_S = 20


def random_psk_base64() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


def _get_node_channel(interface, node_id: str, index: int):
    """Fetch a remote node and block (poll) until its channel list is fully
    synced, returning the mutable Channel proto at `index`. requestChannels()
    itself is fire-and-forget (results stream back via pubsub callbacks that
    populate node.channels once all 8 slots are in), so we poll rather than
    use meshtastic's own getNode(requestChannels=True) — that helper calls
    our_exit()/sys.exit() on timeout, which would kill this worker thread.
    """
    node = interface.getNode(node_id, requestChannels=False)
    node.requestChannels()
    deadline = time.time() + ADMIN_TIMEOUT_S
    while not node.channels and time.time() < deadline:
        time.sleep(0.5)
    if not node.channels or index >= len(node.channels):
        raise RuntimeError(f"node {node_id} did not return channel slot {index}")
    return node, node.channels[index]


def push_channel(interface, node_id: str, index: int, name: str, psk_base64: str,
                  position_precision: int, primary: bool = False) -> None:
    from meshtastic.protobuf import channel_pb2

    node, ch = _get_node_channel(interface, node_id, index)
    ch.role = channel_pb2.Channel.Role.PRIMARY if primary else channel_pb2.Channel.Role.SECONDARY
    ch.settings.name = name
    ch.settings.psk = base64.b64decode(psk_base64)
    ch.settings.module_settings.position_precision = position_precision
    node.writeChannel(index)


def disable_channel(interface, node_id: str, index: int) -> None:
    from meshtastic.protobuf import channel_pb2

    node, ch = _get_node_channel(interface, node_id, index)
    ch.role = channel_pb2.Channel.Role.DISABLED
    node.writeChannel(index)


def set_primary_position_precision(interface, node_id: str, precision: int) -> None:
    push_channel_precision_only(interface, node_id, 0, precision)


def push_channel_precision_only(interface, node_id: str, index: int, precision: int) -> None:
    node, ch = _get_node_channel(interface, node_id, index)
    ch.settings.module_settings.position_precision = precision
    node.writeChannel(index)


def _get_node(interface, node_id: str):
    return interface.getNode(node_id, requestChannels=False)


def push_position_config(interface, node_id: str, gps_update_interval: int,
                          broadcast_secs: int, smart_min_distance: int,
                          smart_min_interval: int) -> None:
    node = _get_node(interface, node_id)
    # requestConfig() blocks (via waitForAckNak) until the remote node
    # replies or raises MeshInterfaceError on timeout — no manual polling needed.
    field = node.localConfig.DESCRIPTOR.fields_by_name["position"]
    node.requestConfig(field)
    pos = node.localConfig.position
    pos.gps_update_interval = gps_update_interval
    pos.position_broadcast_secs = broadcast_secs
    pos.broadcast_smart_minimum_distance = smart_min_distance
    pos.broadcast_smart_minimum_interval_secs = smart_min_interval
    pos.position_broadcast_smart_enabled = True
    node.writeConfig("position")


def push_power_config(interface, node_id: str, is_power_saving: bool, ls_secs: int) -> None:
    node = _get_node(interface, node_id)
    field = node.localConfig.DESCRIPTOR.fields_by_name["power"]
    node.requestConfig(field)
    pw = node.localConfig.power
    pw.is_power_saving = is_power_saving
    pw.ls_secs = ls_secs
    node.writeConfig("power")


def push_buzzer_mode(interface, node_id: str, buzzer_mode: int) -> None:
    node = _get_node(interface, node_id)
    field = node.localConfig.DESCRIPTOR.fields_by_name["device"]
    node.requestConfig(field)
    dev = node.localConfig.device
    dev.buzzer_mode = buzzer_mode
    node.writeConfig("device")


def ring(interface, node_id: str, channel_index: int, text: str = "\U0001f514") -> None:
    interface.sendText(text, destinationId=node_id, channelIndex=channel_index)
