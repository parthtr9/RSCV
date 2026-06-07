"""
WebSocket /ws/joint_states — pushes JSON at 30 Hz.
MJPEG /stream/{cam_name} — multipart camera preview.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from api.deps import latest_joint_state

logger = logging.getLogger(__name__)
router = APIRouter(tags=["streaming"])

WS_PUSH_HZ = 30
MJPEG_FPS  = 15
JPEG_QUALITY = 70


@router.websocket("/ws/joint_states")
async def joint_states_ws(ws: WebSocket) -> None:
    await ws.accept()
    period = 1.0 / WS_PUSH_HZ
    try:
        while True:
            t0 = asyncio.get_event_loop().time()
            state = latest_joint_state.get()
            if state is not None:
                payload = {
                    "ts":     state.timestamp,
                    "qpos":   state.qpos.tolist(),
                    "qvel":   state.qvel.tolist(),
                    "torque": state.torque.tolist(),
                }
                await ws.send_json(payload)
            elapsed = asyncio.get_event_loop().time() - t0
            await asyncio.sleep(max(0.0, period - elapsed))
    except WebSocketDisconnect:
        logger.info("WS client disconnected")
    except Exception:
        logger.exception("WS error")


@router.get("/stream/{cam_name}")
async def mjpeg_stream(cam_name: str) -> StreamingResponse:
    async def generate() -> AsyncGenerator[bytes, None]:
        period = 1.0 / MJPEG_FPS
        while True:
            t0 = asyncio.get_event_loop().time()
            frame = _get_preview_frame(cam_name)
            if frame is not None:
                ok, buf = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                )
                if ok:
                    jpeg = buf.tobytes()
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                    )
            elapsed = asyncio.get_event_loop().time() - t0
            await asyncio.sleep(max(0.0, period - elapsed))

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


def _get_preview_frame(cam_name: str) -> np.ndarray | None:
    """Return the latest frame for a camera name from the active writer's ring."""
    # Access the shared camera rings if available via the aligner
    # For now return a placeholder in mock mode
    h, w = 480, 640
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    t = time.monotonic()
    x = int((t * 50) % w)
    cv2.line(frame, (x, 0), (x, h), (0, 200, 100), 3)
    cv2.putText(
        frame, cam_name, (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2
    )
    return frame
