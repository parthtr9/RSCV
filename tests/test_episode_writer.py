"""HDF5 episode writer: write + readback tests."""
from __future__ import annotations

import time
from pathlib import Path

import h5py
import numpy as np
import pytest

from cameras.sync import AlignedSample
from hardware.damiao import JointState
from recording.episode_writer import EpisodeWriter
from recording.schema import (
    CAMERA_NAMES,
    DS_ACTION,
    DS_QPOS,
    DS_TIMESTAMP,
    ds_image,
)


def make_sample(ts: float, cam_names: tuple[str, ...] = CAMERA_NAMES) -> AlignedSample:
    state = JointState.zeros(timestamp=ts)
    state.qpos[:] = np.linspace(-1.0, 1.0, 8, dtype=np.float32)
    frames = {cam: np.zeros((480, 640, 3), dtype=np.uint8) for cam in cam_names}
    return AlignedSample(
        joint_state=state,
        frames=frames,
        timestamps={cam: ts for cam in cam_names},
        worst_sync_ms=5.0,
    )


@pytest.fixture
def tmp_episode_dir(tmp_path: Path) -> Path:
    return tmp_path / "raw"


class TestEpisodeWriter:
    def test_writes_and_reads_back(self, tmp_episode_dir: Path):
        writer = EpisodeWriter(
            output_dir=tmp_episode_dir,
            task="test task",
            fps=30,
            camera_names=CAMERA_NAMES,
        )
        writer.start()

        n_frames = 10
        for i in range(n_frames):
            sample = make_sample(ts=float(i) * 0.033)
            writer.queue.put(sample)

        path, frames = writer.stop()

        assert frames == n_frames
        assert path.exists()

        with h5py.File(path, "r") as f:
            assert f[DS_TIMESTAMP].shape == (n_frames,)
            assert f[DS_QPOS].shape == (n_frames, 8)
            assert f[DS_ACTION].shape == (n_frames, 8)
            ts = f[DS_TIMESTAMP][:]
            assert ts[0] == pytest.approx(0.0, abs=1e-6)
            assert ts[-1] == pytest.approx(9 * 0.033, abs=1e-4)

    def test_attributes_written(self, tmp_episode_dir: Path):
        writer = EpisodeWriter(
            output_dir=tmp_episode_dir,
            task="pick red cube",
            fps=15,
        )
        writer.start()
        writer.queue.put(make_sample(0.0))
        path, _ = writer.stop()

        with h5py.File(path, "r") as f:
            assert f.attrs["task"] == "pick red cube"
            assert f.attrs["fps"] == 15
            assert f.attrs["robot_type"] == "openarm_2.0"
            assert f.attrs["is_failure"] == False

    def test_is_failure_flag(self, tmp_episode_dir: Path):
        writer = EpisodeWriter(output_dir=tmp_episode_dir, task="fail test")
        writer.start()
        writer.queue.put(make_sample(0.0))
        path, _ = writer.stop(is_failure=True)

        with h5py.File(path, "r") as f:
            assert f.attrs["is_failure"] == True

    def test_image_dataset_shape(self, tmp_episode_dir: Path):
        cam = CAMERA_NAMES[0]
        writer = EpisodeWriter(
            output_dir=tmp_episode_dir, task="shape test",
            camera_names=(cam,),
            frame_shape=(480, 640, 3),
        )
        writer.start()
        for i in range(5):
            writer.queue.put(make_sample(float(i), cam_names=(cam,)))
        path, _ = writer.stop()

        with h5py.File(path, "r") as f:
            ds = f[ds_image(cam)]
            assert ds.shape == (5, 480, 640, 3)

    def test_empty_episode(self, tmp_episode_dir: Path):
        writer = EpisodeWriter(output_dir=tmp_episode_dir, task="empty")
        writer.start()
        path, n = writer.stop()
        assert n == 0
        with h5py.File(path, "r") as f:
            assert f[DS_TIMESTAMP].shape[0] == 0
