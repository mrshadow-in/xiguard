"""WebSocket endpoint — bridges Redis pub/sub to connected dashboards."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.pubsub import CH_ALERTS, CH_CHR_STATUS, CH_STATE, CH_TRAFFIC, get_redis

logger = logging.getLogger(__name__)
router = APIRouter()


class WSManager:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        async with self._lock:
            self.connections.add(ws)
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._pump())

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            self.connections.discard(ws)

    async def _pump(self) -> None:
        redis = get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(CH_TRAFFIC, CH_ALERTS, CH_STATE, CH_CHR_STATUS)
        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                channel = msg["channel"]
                data = msg["data"]
                envelope = {
                    "type": _channel_to_type(channel),
                    "data": _maybe_json(data),
                }
                dead: list[WebSocket] = []
                for ws in list(self.connections):
                    try:
                        await ws.send_json(envelope)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    await self.remove(ws)
        finally:
            try:
                await pubsub.close()
            except Exception:
                pass


def _channel_to_type(channel: str) -> str:
    return {
        CH_TRAFFIC: "traffic_update",
        CH_ALERTS: "alert",
        CH_STATE: "state_change",
        CH_CHR_STATUS: "chr_status",
    }.get(channel, "message")


def _maybe_json(data: str | bytes) -> object:
    import json

    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")
    try:
        return json.loads(data)
    except Exception:
        return data


manager = WSManager()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    await manager.add(websocket)
    try:
        while True:
            # We don't need client messages; keep the socket alive.
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws error")
    finally:
        await manager.remove(websocket)
