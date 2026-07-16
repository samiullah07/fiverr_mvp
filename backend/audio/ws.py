"""WebSocket endpoint for live audio chunk streaming to transcription layer.

This module provides a FastAPI WebSocket endpoint that streams audio chunks
from the capture module to the transcription pipeline.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi import APIRouter
import json
import time
import logging
from typing import Dict, Set
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()

# Track connected clients
connected_clients: Set[WebSocket] = set()


class AudioChunk:
    """Audio chunk with metadata."""

    def __init__(self, data: bytes, timestamp: float, source: str = "mic"):
        self.data = data
        self.timestamp = timestamp
        self.source = source  # "mic" or "loopback"

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "chunk_size_bytes": len(self.data)
        }


@router.websocket("/ws/audio")
async def websocket_audio_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for streaming audio chunks.

    Clients connect and receive audio chunk metadata.
    Audio data should be sent by the capture system via the process_audio_chunk method.
    """
    await websocket.accept()
    connected_clients.add(websocket)

    try:
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            # Acknowledge client messages
            await websocket.send_text(json.dumps({"status": "connected", "timestamp": time.time()}))
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
        logger.info("Client disconnected from audio WebSocket")
    except Exception as e:
        logger.error(f"Audio WebSocket error: {e}")
        connected_clients.discard(websocket)


async def broadcast_audio_chunk(chunk: AudioChunk):
    """
    Broadcast an audio chunk to all connected WebSocket clients.

    Args:
        chunk: AudioChunk object containing audio data and metadata
    """
    if not connected_clients:
        logger.debug("No connected WebSocket clients")
        return

    # Serialize chunk metadata
    msg = json.dumps({
        "type": "audio_chunk",
        "data": chunk.to_dict(),
        "timestamp": time.time()
    })

    # Send to all clients
    disconnected = set()
    for client in connected_clients:
        try:
            await client.send_text(msg)
        except Exception as e:
            logger.warning(f"Failed to send to client: {e}")
            disconnected.add(client)

    # Clean up disconnected clients
    connected_clients -= disconnected


def get_router() -> APIRouter:
    """Return the audio router for FastAPI app."""
    return router


if __name__ == "__main__":
    # Test WebSocket server
    import uvicorn

    app = FastAPI()
    app.include_router(get_router())

    uvicorn.run(app, host="localhost", port=8001)