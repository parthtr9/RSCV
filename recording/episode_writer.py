"""
HDF5 episode writer.
Single writer thread owns the file handle for the entire episode.
Pre-allocates datasets with maxshape=(None, ...) and extends with resize().
"""
from __future__ import annotations

import datetime
import logging
import os
import queue
import threading
import time
import uuid
from pathlib import Path

import h5py
import numpy as np

from cameras.sync import AlignedSample
from recording.schema import (
    ATTR_CREATED_AT,
    ATTR_FPS,
    ATTR_IS_FAILURE,
    ATTR_ROBOT_TYPE,
    ATTR_SYNC_METHOD,
    ATTR_SYNC_TOL,
    ATTR_TASK,
    CAMERA_NAMES,
    DEFAULT_FPS,
    DEFAULT_FRAME_SHAPE,
    FLUSH_EVERY_N_FRAMES,
    ROBOT_TYPE,
    DatasetSpec,
    build_dataset_specs,
    ds_image,
    DS_TIMESTAMP,
    DS_QPOS,
    DS_QVEL,
    DS_TORQUE,
    DS_ACTION,
)

logger = logging.getLogger(__name__)

INITIAL_ALLOC = 256  # pre-allocate this many frames


class EpisodeWriter:
    """
    Writes a single HDF5 episode from an AlignedSample queue.

    Usage:
        writer = EpisodeWriter(output_dir=Path("data/raw"), task="pick red cube")
        writer.start()
        # producer pushes AlignedSample objects into writer.queue
        path, n_frames = writer.stop()
    """

    def __init__(
        self,
        output_dir: Path,
        task: str,
        fps: int = DEFAULT_FPS,
        camera_names: tuple[str, ...] = CAMERA_NAMES,
        frame_shape: tuple[int, int, int] = DEFAULT_FRAME_SHAPE,
        sync_method: str = "nearest_neighbour_host_ts",
    ) -> None:
        self.queue: queue.Queue[AlignedSample] = queue.Queue(maxsize=10)
        self._output_dir = output_dir
        self._task = task
        self._fps = fps
        self._camera_names = camera_names
        self._frame_shape = frame_shape
        self._sync_method = sync_method

        self.episode_id = str(uuid.uuid4())
        self._path = output_dir / f"episode_{self.episode_id[:8]}.hdf5"

        self._thread: threading.Thread | None = None
        self._running = False
        self._n_frames = 0
        self._worst_sync_ms = 0.0
        self._specs = build_dataset_specs(camera_names, frame_shape)

    def start(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._thread = threading.Thread(
            target=self._write_loop, daemon=True, name="hdf5-writer"
        )
        self._thread.start()
        logger.info("EpisodeWriter started → %s", self._path)

    def stop(self, is_failure: bool = False) -> tuple[Path, int]:
        """Signal stop, wait for writer thread, finalize file. Returns (path, n_frames)."""
        self._running = False
        self.queue.put(None)  # type: ignore[arg-type]  # sentinel
        if self._thread:
            self._thread.join(timeout=10.0)
        logger.info(
            "Episode %s finalized: %d frames, worst_sync=%.1f ms",
            self.episode_id,
            self._n_frames,
            self._worst_sync_ms,
        )
        self._patch_attributes(is_failure)
        return self._path, self._n_frames

    def _write_loop(self) -> None:
        with h5py.File(self._path, "w") as f:
            datasets = self._preallocate(f)
            n = 0

            while True:
                try:
                    sample = self.queue.get(timeout=0.1)
                except queue.Empty:
                    if not self._running:
                        break
                    continue

                if sample is None:
                    break

                self._extend_if_needed(datasets, n)
                self._write_sample(datasets, n, sample)
                self._worst_sync_ms = max(self._worst_sync_ms, sample.worst_sync_ms)
                n += 1

                if n % FLUSH_EVERY_N_FRAMES == 0:
                    f.flush()

            # trim to actual length
            for ds in datasets.values():
                if ds.shape[0] != n:
                    ds.resize(n, axis=0)

            f.flush()
            try:
                os.fsync(f.id.get_vfd_handle())
            except Exception:
                pass

        self._n_frames = n

    def _preallocate(self, f: h5py.File) -> dict[str, h5py.Dataset]:
        datasets: dict[str, h5py.Dataset] = {}
        created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        f.attrs[ATTR_TASK]        = self._task
        f.attrs[ATTR_FPS]         = self._fps
        f.attrs[ATTR_ROBOT_TYPE]  = ROBOT_TYPE
        f.attrs[ATTR_IS_FAILURE]  = False
        f.attrs[ATTR_CREATED_AT]  = created_at
        f.attrs[ATTR_SYNC_TOL]    = 0.0  # updated at stop()
        f.attrs[ATTR_SYNC_METHOD] = self._sync_method

        for spec in self._specs:
            maxshape = (None,) + spec.shape_per_frame
            initial  = (INITIAL_ALLOC,) + spec.shape_per_frame
            group_path = "/".join(spec.path.split("/")[:-1])
            if group_path:
                f.require_group(group_path)
            ds = f.create_dataset(
                spec.path,
                shape=initial,
                maxshape=maxshape,
                dtype=spec.dtype,
                chunks=True,
                compression="lzf",
            )
            datasets[spec.path] = ds

        return datasets

    def _extend_if_needed(self, datasets: dict[str, h5py.Dataset], n: int) -> None:
        if n >= datasets[DS_TIMESTAMP].shape[0]:
            new_size = datasets[DS_TIMESTAMP].shape[0] + INITIAL_ALLOC
            for ds in datasets.values():
                ds.resize(new_size, axis=0)

    def _write_sample(
        self,
        datasets: dict[str, h5py.Dataset],
        n: int,
        sample: AlignedSample,
    ) -> None:
        js = sample.joint_state
        datasets[DS_TIMESTAMP][n] = js.timestamp
        datasets[DS_QPOS][n]      = js.qpos
        datasets[DS_QVEL][n]      = js.qvel
        datasets[DS_TORQUE][n]    = js.torque
        datasets[DS_ACTION][n]    = js.qpos  # commanded = current in mock; replace with leader

        for cam in self._camera_names:
            frame = sample.frames.get(cam)
            if frame is not None:
                datasets[ds_image(cam)][n] = frame

    def _patch_attributes(self, is_failure: bool) -> None:
        with h5py.File(self._path, "a") as f:
            f.attrs[ATTR_IS_FAILURE] = is_failure
            f.attrs[ATTR_SYNC_TOL]   = self._worst_sync_ms
