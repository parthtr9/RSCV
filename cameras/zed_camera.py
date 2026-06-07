"""
ZED stereo camera — LEFT RGB + DEPTH via pyzed.sl.
Run one thread per ZED. Never call from asyncio.
"""
from __future__ import annotations

import logging
import time

import numpy as np

from cameras.base import CameraSource

logger = logging.getLogger(__name__)


class ZEDCamera(CameraSource):
    def __init__(
        self,
        name: str = "cam_zed_left",
        resolution: str = "HD720",
        fps: int = 30,
    ) -> None:
        self.name = name
        self._resolution_str = resolution
        self._fps = fps
        self._zed: object | None = None  # pyzed.sl.Camera

    def open(self) -> None:
        try:
            import pyzed.sl as sl
        except ImportError as e:
            raise RuntimeError(
                "pyzed not installed. Install from stereolabs.com ZED SDK."
            ) from e

        self._zed = sl.Camera()
        params = sl.InitParameters()
        params.camera_resolution = getattr(sl.RESOLUTION, self._resolution_str)
        params.camera_fps = self._fps
        params.depth_mode = sl.DEPTH_MODE.PERFORMANCE

        err = self._zed.open(params)  # type: ignore[union-attr]
        if err != sl.ERROR_CODE.SUCCESS:
            raise RuntimeError(f"ZED open failed: {err}")

        self._mat_left  = sl.Mat()
        self._mat_depth = sl.Mat()
        logger.info("ZEDCamera %s opened (%s @ %d fps)", self.name, self._resolution_str, self._fps)

    def grab(self) -> tuple[np.ndarray, float]:
        import pyzed.sl as sl

        if self._zed is None:
            raise RuntimeError("ZEDCamera not open")

        rt = sl.RuntimeParameters()
        if self._zed.grab(rt) != sl.ERROR_CODE.SUCCESS:  # type: ignore[union-attr]
            raise RuntimeError("ZED grab failed")

        ts_ns = self._zed.get_timestamp(sl.TIME_REFERENCE.IMAGE).get_nanoseconds()  # type: ignore[union-attr]
        ts = ts_ns * 1e-9  # convert to seconds (wall clock from ZED)

        self._zed.retrieve_image(self._mat_left, sl.VIEW.LEFT)  # type: ignore[union-attr]
        frame_bgra = self._mat_left.get_data()
        frame = frame_bgra[:, :, :3].copy()  # drop alpha → BGR

        return frame, ts

    def close(self) -> None:
        if self._zed is not None:
            self._zed.close()  # type: ignore[union-attr]
            self._zed = None
        logger.info("ZEDCamera %s closed", self.name)
