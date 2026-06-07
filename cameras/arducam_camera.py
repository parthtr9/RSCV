"""
Arducam USB camera via cv2.VideoCapture.
Identifies camera by udev serial ID — never by /dev/video* index.
"""
from __future__ import annotations

import logging
import time

import cv2
import numpy as np

from cameras.base import CameraSource

logger = logging.getLogger(__name__)


def _serial_to_devnode(serial: str) -> str | None:
    """Resolve udev serial ID → /dev/videoN path."""
    try:
        import pyudev
        ctx = pyudev.Context()
        for dev in ctx.list_devices(subsystem="video4linux"):
            if dev.get("ID_SERIAL_SHORT") == serial:
                return dev.device_node
    except ImportError:
        logger.warning("pyudev not available, falling back to index 0")
    return None


class ArducamCamera(CameraSource):
    def __init__(
        self,
        name: str,
        serial: str,
        width: int = 640,
        height: int = 480,
        fps: int = 60,
    ) -> None:
        self.name = name
        self._serial = serial
        self._width = width
        self._height = height
        self._fps = fps
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        if self._cap and self._cap.isOpened():
            return

        devnode = _serial_to_devnode(self._serial)
        if devnode is None:
            raise RuntimeError(f"Camera serial {self._serial!r} not found via udev")

        self._cap = cv2.VideoCapture(devnode)
        if not self._cap.isOpened():
            raise RuntimeError(f"Failed to open {devnode}")

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        self._cap.set(cv2.CAP_PROP_FPS, self._fps)
        logger.info("ArducamCamera %s opened at %s", self.name, devnode)

    def grab(self) -> tuple[np.ndarray, float]:
        if self._cap is None or not self._cap.isOpened():
            raise RuntimeError(f"Camera {self.name} not open")

        ret, frame = self._cap.read()
        ts = time.monotonic()  # host timestamp post-grab (~30-60 ms jitter)

        if not ret or frame is None:
            raise RuntimeError(f"Camera {self.name} failed to read frame")

        return frame, ts  # BGR HWC uint8

    def close(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None
        logger.info("ArducamCamera %s closed", self.name)
