"""Abstract camera interface."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

import numpy as np


class CameraSource(ABC):
    """All cameras implement this interface."""

    name: str  # logical name, e.g. "cam_left_wrist"

    @abstractmethod
    def open(self) -> None:
        """Open device. Idempotent."""

    @abstractmethod
    def grab(self) -> tuple[np.ndarray, float]:
        """
        Capture one frame.
        Returns (frame_HWC_uint8, monotonic_timestamp_seconds).
        """

    @abstractmethod
    def close(self) -> None:
        """Release device. Idempotent."""

    def __enter__(self) -> "CameraSource":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
