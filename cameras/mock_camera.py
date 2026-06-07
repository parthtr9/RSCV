"""Synthetic camera for mock/dev mode — no hardware required."""
from __future__ import annotations

import time

import numpy as np

from cameras.base import CameraSource


class MockCamera(CameraSource):
    def __init__(
        self,
        name: str,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        color: tuple[int, int, int] = (0, 120, 200),
    ) -> None:
        self.name = name
        self._width = width
        self._height = height
        self._fps = fps
        self._color = color
        self._frame_idx = 0
        self._opened = False

    def open(self) -> None:
        self._opened = True
        self._frame_idx = 0

    def grab(self) -> tuple[np.ndarray, float]:
        if not self._opened:
            raise RuntimeError(f"MockCamera {self.name} not open")

        # Synthetic frame: solid color with frame counter overlay
        frame = np.full((self._height, self._width, 3), self._color, dtype=np.uint8)

        # Add a moving gradient stripe so frames visually differ
        stripe_y = int((self._frame_idx * 4) % self._height)
        frame[stripe_y : stripe_y + 8, :] = 255

        self._frame_idx += 1
        ts = time.monotonic()

        time.sleep(1.0 / self._fps)  # simulate capture latency
        return frame, ts

    def close(self) -> None:
        self._opened = False
