"""
Multi-camera nearest-neighbour aligner.

Each camera thread pushes (frame, ts) into its ring buffer.
The aligner ticks at `fps` Hz, uses the latest joint state as the leader
timestamp, and picks the nearest frame from each ring.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass

import numpy as np

from hardware.damiao import JointState

logger = logging.getLogger(__name__)


@dataclass
class AlignedSample:
    joint_state: JointState
    frames: dict[str, np.ndarray]   # cam_name → HWC uint8
    timestamps: dict[str, float]    # cam_name → monotonic ts
    worst_sync_ms: float            # max |cam_ts - leader_ts| * 1000


class CameraRing:
    """Thread-safe ring buffer for (frame, ts) pairs."""

    def __init__(self, maxlen: int = 120) -> None:
        self._ring: deque[tuple[np.ndarray, float]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray, ts: float) -> None:
        with self._lock:
            self._ring.append((frame, ts))

    def nearest(self, t_leader: float) -> tuple[np.ndarray, float] | None:
        with self._lock:
            if not self._ring:
                return None
            return min(self._ring, key=lambda item: abs(item[1] - t_leader))


class MultiCameraAligner:
    """
    Aligns multi-camera frames to joint state leader at a fixed tick rate.

    Usage:
        aligner = MultiCameraAligner(rings, joint_queue, aligned_queue, fps=30)
        aligner.start()
        # ...
        aligner.stop()
    """

    def __init__(
        self,
        rings: dict[str, CameraRing],
        joint_queue: "queue.Queue[JointState]",
        aligned_queue: "queue.Queue[AlignedSample]",
        fps: int = 30,
        sync_tolerance_ms: float = 15.0,
    ) -> None:
        self._rings = rings
        self._joint_queue = joint_queue
        self._aligned_queue = aligned_queue
        self._fps = fps
        self._sync_tol_ms = sync_tolerance_ms
        self._latest_state: JointState | None = None
        self._running = False
        self._thread = threading.Thread(target=self._run, daemon=True, name="aligner")
        # Drains joint_queue asynchronously to always have latest state
        self._drain_thread = threading.Thread(
            target=self._drain_joint_queue, daemon=True, name="aligner-drain"
        )

    def start(self) -> None:
        self._running = True
        self._drain_thread.start()
        self._thread.start()
        logger.info("MultiCameraAligner started at %d Hz", self._fps)

    def stop(self) -> None:
        self._running = False
        self._thread.join(timeout=2.0)
        self._drain_thread.join(timeout=2.0)
        logger.info("MultiCameraAligner stopped")

    def _drain_joint_queue(self) -> None:
        while self._running:
            try:
                state = self._joint_queue.get(timeout=0.05)
                self._latest_state = state
            except queue.Empty:
                continue

    def _run(self) -> None:
        period = 1.0 / self._fps
        next_tick = time.monotonic()

        while self._running:
            now = time.monotonic()
            if now < next_tick:
                time.sleep(next_tick - now)
            next_tick += period

            state = self._latest_state
            if state is None:
                continue

            t_leader = state.timestamp
            frames: dict[str, np.ndarray] = {}
            timestamps: dict[str, float] = {}
            worst_ms = 0.0

            ok = True
            for cam_name, ring in self._rings.items():
                result = ring.nearest(t_leader)
                if result is None:
                    logger.warning("Ring %s empty", cam_name)
                    ok = False
                    break
                frame, cam_ts = result
                diff_ms = abs(cam_ts - t_leader) * 1000.0
                if diff_ms > self._sync_tol_ms:
                    logger.warning(
                        "Sync warning %s: %.1f ms off leader", cam_name, diff_ms
                    )
                worst_ms = max(worst_ms, diff_ms)
                frames[cam_name] = frame
                timestamps[cam_name] = cam_ts

            if not ok:
                continue

            sample = AlignedSample(
                joint_state=state,
                frames=frames,
                timestamps=timestamps,
                worst_sync_ms=worst_ms,
            )
            try:
                self._aligned_queue.put_nowait(sample)
            except queue.Full:
                logger.warning("aligned_queue full, dropping sample")
