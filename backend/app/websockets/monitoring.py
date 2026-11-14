"""Connection management for live monitoring events."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect


logger = logging.getLogger(__name__)


class MonitoringConnectionManager:
    """Track connected clients and broadcast events without coupling client failures."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a WebSocket on its serving event loop."""
        await websocket.accept()
        with self._lock:
            self._clients.add(websocket)
            self._loop = asyncio.get_running_loop()
        logger.info("Monitoring WebSocket connected; %d client(s) active.", self.client_count)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a client safely, including repeated disconnect notifications."""
        with self._lock:
            self._clients.discard(websocket)
            if not self._clients:
                self._loop = None
        logger.info("Monitoring WebSocket disconnected; %d client(s) active.", self.client_count)

    @property
    def client_count(self) -> int:
        """Return the number of registered clients."""
        with self._lock:
            return len(self._clients)

    def publish(self, event: dict[str, Any]) -> None:
        """Schedule a broadcast from synchronous REST or simulation code."""
        with self._lock:
            loop = self._loop
            connected = bool(self._clients)
        if not connected:
            return
        if loop is None or loop.is_closed():
            logger.error("Monitoring clients are connected but the broadcast event loop is unavailable.")
            return
        coroutine = self.broadcast(event)
        try:
            asyncio.run_coroutine_threadsafe(coroutine, loop)
        except RuntimeError:
            coroutine.close()
            logger.exception("Could not schedule monitoring WebSocket broadcast.")

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send an event to every connected client and isolate individual failures."""
        with self._lock:
            clients = tuple(self._clients)
        for websocket in clients:
            try:
                await websocket.send_json(event)
            except WebSocketDisconnect:
                logger.info("Monitoring WebSocket disconnected during broadcast.")
                self.disconnect(websocket)
            except Exception:
                logger.exception("Monitoring WebSocket send failed; removing client.")
                self.disconnect(websocket)


connection_manager = MonitoringConnectionManager()
