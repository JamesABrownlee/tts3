"""In-memory websocket broker for OBS/browser clients."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from fastapi import WebSocket


class OBSBroker:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)

    async def broadcast(self, payload: dict[str, object]) -> int:
        async with self._lock:
            clients = list(self._clients)
        if not clients:
            return 0
        delivered = 0
        for client in clients:
            try:
                await client.send_json(payload)
                delivered += 1
            except Exception:
                await self.disconnect(client)
        return delivered
