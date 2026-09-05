import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from ..auth import require_login
from ..db import get_session
from ..models import Channel, Gateway, User
from ..schemas import ChannelIn, ChannelPushIn
from ..services import mesh_admin
from ..services.mesh_manager import mesh_manager

log = logging.getLogger("pawtrack.channels")

router = APIRouter(prefix="/api/channels", tags=["channels"])


def _user_gateway_ids(session, owner_id: int) -> list[int]:
    return [g.id for g in session.exec(select(Gateway).where(Gateway.owner_id == owner_id)).all()]


@router.get("")
def list_channels(user: User = Depends(require_login)):
    with get_session() as session:
        return session.exec(select(Channel).where(Channel.owner_id == user.id)).all()


@router.post("")
def create_channel(payload: ChannelIn, user: User = Depends(require_login)):
    data = payload.model_dump()
    if not data.get("psk_base64"):
        data["psk_base64"] = mesh_admin.random_psk_base64()
    with get_session() as session:
        ch = Channel(owner_id=user.id, **data)
        session.add(ch)
        session.commit()
        session.refresh(ch)
        return ch


@router.put("/{channel_id}")
def update_channel(channel_id: int, payload: ChannelIn, user: User = Depends(require_login)):
    with get_session() as session:
        ch = session.get(Channel, channel_id)
        if not ch or ch.owner_id != user.id:
            raise HTTPException(status_code=404, detail="not_found")
        data = payload.model_dump()
        if not data.get("psk_base64"):
            data["psk_base64"] = ch.psk_base64
        for k, v in data.items():
            setattr(ch, k, v)
        session.add(ch)
        session.commit()
        session.refresh(ch)
        return ch


@router.delete("/{channel_id}")
def delete_channel(channel_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        ch = session.get(Channel, channel_id)
        if not ch or ch.owner_id != user.id:
            raise HTTPException(status_code=404, detail="not_found")
        session.delete(ch)
        session.commit()
    return {"ok": True}


@router.post("/{channel_id}/push")
def push_channel(channel_id: int, payload: ChannelPushIn, user: User = Depends(require_login)):
    with get_session() as session:
        ch = session.get(Channel, channel_id)
        if not ch or ch.owner_id != user.id:
            raise HTTPException(status_code=404, detail="not_found")
        gw_ids = _user_gateway_ids(session, user.id)
        # every raw-node_id target must belong to a gateway this user owns —
        # otherwise a user could push config to another account's gateway ID
        allowed_gateway_targets = {f"gateway:{gid}" for gid in gw_ids}

    results = {}
    for target in payload.targets:
        if target.startswith("gateway:"):
            if target not in allowed_gateway_targets:
                results[target] = "not_found"
                continue
            gateway_id = int(target.split(":", 1)[1])
            interface = mesh_manager.get_interface_for_gateway(gateway_id)
            node_id = "^local"
        else:
            interface = mesh_manager.get_active_interface(gateway_ids=gw_ids)
            node_id = target

        if interface is None:
            results[target] = "gateway_offline"
            continue
        try:
            mesh_admin.push_channel(
                interface, node_id, ch.device_index, ch.name, ch.psk_base64,
                ch.position_precision, primary=payload.primary,
            )
            results[target] = "ok"
        except Exception as e:
            log.warning("push channel to %s failed: %s", target, e)
            results[target] = f"error: {e}"
    return {"results": results}
