import asyncio
import json

from fastapi import WebSocket


class WSManager:
    def __init__(self) -> None:
        # ws -> (user_id, role)
        self._clients: dict[WebSocket, tuple[int, str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, user_id: int, role: str) -> None:
        await ws.accept()
        async with self._lock:
            self._clients[ws] = (user_id, role)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.pop(ws, None)

    async def _send_all(self, targets: list[WebSocket], payload: dict) -> None:
        data = json.dumps(payload, default=str)
        dead = []
        for ws in targets:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.pop(ws, None)

    async def broadcast_admin(self, payload: dict) -> None:
        """Send to every connected admin — used for cross-user events like
        another user's device location."""
        async with self._lock:
            targets = [ws for ws, (_, role) in self._clients.items() if role == "admin"]
        await self._send_all(targets, payload)

    async def broadcast_owner(self, payload: dict, owner_id: int) -> None:
        """Send to the resource owner and every admin — never to other
        regular users, since positions/alerts are private to their owner."""
        async with self._lock:
            targets = [ws for ws, (uid, role) in self._clients.items() if uid == owner_id or role == "admin"]
        await self._send_all(targets, payload)


ws_manager = WSManager()
