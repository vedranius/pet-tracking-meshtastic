from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import select

from ..db import get_session
from ..models import User
from ..services.ws_manager import ws_manager

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    user_id = websocket.session.get("user_id")
    if not user_id:
        await websocket.close(code=4401)
        return
    with get_session() as session:
        user = session.get(User, user_id)
    if not user:
        await websocket.close(code=4401)
        return
    await ws_manager.connect(websocket, user.id, user.role)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket)
