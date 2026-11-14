"""Live monitoring WebSocket endpoint."""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websockets.monitoring import connection_manager


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Live monitoring"])


@router.websocket("/ws/monitoring")
async def monitoring_updates(websocket: WebSocket) -> None:
    """Keep the client connected to receive live reading and dashboard events."""
    await connection_manager.connect(websocket)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        logger.info("Monitoring WebSocket client closed its connection.")
    finally:
        connection_manager.disconnect(websocket)
