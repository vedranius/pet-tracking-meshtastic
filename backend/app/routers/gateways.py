from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from ..auth import require_login
from ..db import get_session
from ..models import Gateway, User
from ..schemas import GatewayIn
from ..services.mesh_manager import mesh_manager

router = APIRouter(prefix="/api/gateways", tags=["gateways"])


@router.get("")
def list_gateways(user: User = Depends(require_login)):
    with get_session() as session:
        return session.exec(select(Gateway).where(Gateway.owner_id == user.id)).all()


@router.post("")
def create_gateway(payload: GatewayIn, user: User = Depends(require_login)):
    with get_session() as session:
        gw = Gateway(owner_id=user.id, **payload.model_dump())
        session.add(gw)
        session.commit()
        session.refresh(gw)
    if gw.enabled:
        mesh_manager.add_gateway(gw.id, gw.ip_address)
    return gw


@router.put("/{gateway_id}")
def update_gateway(gateway_id: int, payload: GatewayIn, user: User = Depends(require_login)):
    with get_session() as session:
        gw = session.get(Gateway, gateway_id)
        if not gw or gw.owner_id != user.id:
            raise HTTPException(status_code=404, detail="not_found")
        for k, v in payload.model_dump().items():
            setattr(gw, k, v)
        session.add(gw)
        session.commit()
        session.refresh(gw)
    if gw.enabled:
        mesh_manager.add_gateway(gw.id, gw.ip_address)
    else:
        mesh_manager.remove_gateway(gw.id)
    return gw


@router.delete("/{gateway_id}")
def delete_gateway(gateway_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        gw = session.get(Gateway, gateway_id)
        if not gw or gw.owner_id != user.id:
            raise HTTPException(status_code=404, detail="not_found")
        mesh_manager.remove_gateway(gateway_id)
        session.delete(gw)
        session.commit()
    return {"ok": True}


@router.get("/{gateway_id}/nodes")
def gateway_nodes(gateway_id: int, user: User = Depends(require_login)):
    with get_session() as session:
        gw = session.get(Gateway, gateway_id)
        if not gw or gw.owner_id != user.id:
            raise HTTPException(status_code=404, detail="not_found")
    return mesh_manager.get_known_nodes(gateway_id)
