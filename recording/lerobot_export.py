"""
HDF5 episode → LeRobot v2 (Parquet + MP4) converter.

Usage:
    python -m recording.lerobot_export \
        --input data/raw/ \
        --output data/lerobot/ \
        --task "pick and place"
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import h5py
import numpy as np

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    HAS_ARROW = True
except ImportError:
    HAS_ARROW = False

from recording.schema import (
    ATTR_FPS,
    ATTR_TASK,
    CAMERA_NAMES,
    DS_ACTION,
    DS_QPOS,
    DS_TIMESTAMP,
    ds_image,
)

logger = logging.getLogger(__name__)


def export_episode(
    hdf5_path: Path,
    out_dir: Path,
    episode_index: int,
    task: str | None = None,
) -> dict[str, object]:
    """
    Convert one HDF5 episode to LeRobot v2 Parquet + MP4 files.
    Returns episode metadata dict.
    """
    if not HAS_ARROW:
        raise RuntimeError("pyarrow required: pip install pyarrow")

    out_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir = out_dir / "data" / "chunk-000"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    with h5py.File(hdf5_path, "r") as f:
        fps       = int(f.attrs.get(ATTR_FPS, 30))
        ep_task   = task or str(f.attrs.get(ATTR_TASK, "unknown"))
        qpos      = f[DS_QPOS][:]       # (T, 8)
        action    = f[DS_ACTION][:]     # (T, 8)
        timestamp = f[DS_TIMESTAMP][:]  # (T,)
        T = len(timestamp)

        cam_frames: dict[str, np.ndarray] = {}
        for cam in CAMERA_NAMES:
            key = ds_image(cam)
            if key in f:
                cam_frames[cam] = f[key][:]

    # ── Write MP4 per camera ──────────────────────────────────────────────────
    vid_dir = out_dir / "videos" / "chunk-000"
    for cam, frames in cam_frames.items():
        cam_vid_dir = vid_dir / f"observation.images.{cam}"
        cam_vid_dir.mkdir(parents=True, exist_ok=True)
        mp4_path = cam_vid_dir / f"episode_{episode_index:06d}.mp4"
        _write_mp4(frames, mp4_path, fps)

    # ── Normalize timestamps → frame-relative ────────────────────────────────
    t_rel = timestamp - timestamp[0]

    # ── Build Parquet ─────────────────────────────────────────────────────────
    rows = {
        "observation.state": pa.array(list(qpos),   type=pa.list_(pa.float32(), 8)),
        "action":            pa.array(list(action),  type=pa.list_(pa.float32(), 8)),
        "timestamp":         pa.array(t_rel,         type=pa.float64()),
        "episode_index":     pa.array([episode_index] * T, type=pa.int32()),
        "frame_index":       pa.array(list(range(T)),       type=pa.int32()),
        "next.done":         pa.array([False] * (T - 1) + [True], type=pa.bool_()),
        "task_index":        pa.array([0] * T,              type=pa.int32()),
    }
    table = pa.table(rows)
    pq_path = chunk_dir / f"episode_{episode_index:06d}.parquet"
    pq.write_table(table, pq_path, compression="snappy")

    logger.info("Exported episode %d → %s (%d frames)", episode_index, pq_path, T)

    return {
        "episode_index": episode_index,
        "length": T,
        "fps": fps,
        "task": ep_task,
        "hdf5": str(hdf5_path),
    }


def _write_mp4(frames: np.ndarray, path: Path, fps: int) -> None:
    """Write (T, H, W, 3) uint8 BGR frames to MP4 via OpenCV."""
    T, H, W, C = frames.shape
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (W, H))
    try:
        for frame in frames:
            writer.write(frame)
    finally:
        writer.release()


def export_dataset(input_dir: Path, output_dir: Path, task: str) -> None:
    hdf5_files = sorted(input_dir.glob("episode_*.hdf5"))
    if not hdf5_files:
        logger.warning("No HDF5 files found in %s", input_dir)
        return

    metas = []
    for idx, h5path in enumerate(hdf5_files):
        meta = export_episode(h5path, output_dir, episode_index=idx, task=task)
        metas.append(meta)

    # ── Write meta/info.json ──────────────────────────────────────────────────
    meta_dir = output_dir / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    info = {
        "fps": metas[0]["fps"] if metas else 30,
        "total_episodes": len(metas),
        "total_frames": sum(m["length"] for m in metas),
        "robot_type": "openarm_2.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (meta_dir / "info.json").write_text(json.dumps(info, indent=2))

    # ── Write meta/tasks.jsonl ────────────────────────────────────────────────
    (meta_dir / "tasks.jsonl").write_text(
        json.dumps({"task_index": 0, "task": task}) + "\n"
    )

    # ── Write meta/episodes/stats.jsonl ──────────────────────────────────────
    stats_dir = meta_dir / "episodes"
    stats_dir.mkdir(exist_ok=True)
    with open(stats_dir / "stats.jsonl", "w") as fout:
        for m in metas:
            fout.write(json.dumps(m) + "\n")

    logger.info("Dataset export complete: %d episodes → %s", len(metas), output_dir)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task",   type=str,  required=True)
    args = parser.parse_args()
    export_dataset(args.input, args.output, args.task)
