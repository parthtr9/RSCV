"""Nearest-neighbour aligner correctness tests."""
from __future__ import annotations

import queue
import time

import numpy as np
import pytest

from cameras.sync import AlignedSample, CameraRing, MultiCameraAligner
from hardware.damiao import JointState


def make_state(ts: float) -> JointState:
    return JointState.zeros(timestamp=ts)


def make_frame(val: int = 0) -> np.ndarray:
    return np.full((480, 640, 3), val, dtype=np.uint8)


class TestCameraRing:
    def test_push_and_nearest(self):
        ring = CameraRing(maxlen=10)
        ring.push(make_frame(0), 1.0)
        ring.push(make_frame(1), 2.0)
        ring.push(make_frame(2), 3.0)
        frame, ts = ring.nearest(2.1)  # type: ignore[misc]
        assert ts == 2.0

    def test_empty_ring_returns_none(self):
        ring = CameraRing()
        assert ring.nearest(1.0) is None

    def test_maxlen_evicts_old(self):
        ring = CameraRing(maxlen=3)
        for i in range(5):
            ring.push(make_frame(i), float(i))
        frame, ts = ring.nearest(0.0)  # type: ignore[misc]
        assert ts >= 2.0  # oldest 0, 1 evicted

    def test_nearest_picks_closest(self):
        ring = CameraRing()
        ring.push(make_frame(), 1.0)
        ring.push(make_frame(), 1.5)
        ring.push(make_frame(), 2.0)
        _, ts = ring.nearest(1.3)  # type: ignore[misc]
        assert ts == 1.5

    def test_thread_safe_concurrent_push(self):
        import threading
        ring = CameraRing(maxlen=1000)
        errors: list[Exception] = []

        def pusher():
            for i in range(100):
                try:
                    ring.push(make_frame(), float(i) * 0.001)
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=pusher) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


class TestMultiCameraAligner:
    def test_produces_aligned_sample(self):
        rings = {
            "cam_a": CameraRing(),
            "cam_b": CameraRing(),
        }
        joint_q: queue.Queue[JointState] = queue.Queue()
        aligned_q: queue.Queue[AlignedSample] = queue.Queue()

        aligner = MultiCameraAligner(rings, joint_q, aligned_q, fps=10, sync_tolerance_ms=50.0)
        aligner.start()

        now = time.monotonic()
        rings["cam_a"].push(make_frame(10), now)
        rings["cam_b"].push(make_frame(20), now)
        joint_q.put(make_state(now))

        try:
            sample = aligned_q.get(timeout=1.0)
            assert "cam_a" in sample.frames
            assert "cam_b" in sample.frames
            assert sample.worst_sync_ms < 100.0
        finally:
            aligner.stop()

    def test_no_sample_when_ring_empty(self):
        rings = {"cam_a": CameraRing()}
        joint_q: queue.Queue[JointState] = queue.Queue()
        aligned_q: queue.Queue[AlignedSample] = queue.Queue()

        aligner = MultiCameraAligner(rings, joint_q, aligned_q, fps=10)
        aligner.start()

        now = time.monotonic()
        joint_q.put(make_state(now))
        # cam_a ring empty → no sample emitted

        with pytest.raises(queue.Empty):
            aligned_q.get(timeout=0.3)

        aligner.stop()
