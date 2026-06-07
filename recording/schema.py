"""Episode schema constants — dataset keys, dtypes, shapes."""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

# ── Camera names (must match config/default.yaml) ────────────────────────────
CAMERA_NAMES: tuple[str, ...] = (
    "cam_left_wrist",
    "cam_right_wrist",
    "cam_ceiling",
    "cam_zed_left",
)

# ── Default frame shape (H, W, C) — can be overridden at episode creation ────
DEFAULT_FRAME_SHAPE = (480, 640, 3)

NUM_JOINTS = 8

# ── HDF5 dataset paths ────────────────────────────────────────────────────────
DS_TIMESTAMP = "timestamp"
DS_QPOS      = "observations/qpos"
DS_QVEL      = "observations/qvel"
DS_TORQUE    = "observations/torque"
DS_ACTION    = "action"

def ds_image(cam: str) -> str:
    return f"observations/images/{cam}"


# ── Root attribute keys ───────────────────────────────────────────────────────
ATTR_TASK       = "task"
ATTR_FPS        = "fps"
ATTR_ROBOT_TYPE = "robot_type"
ATTR_IS_FAILURE = "is_failure"
ATTR_CREATED_AT = "created_at"
ATTR_SYNC_TOL   = "sync_tol_ms"
ATTR_SYNC_METHOD = "sync_method"

ROBOT_TYPE = "openarm_2.0"
DEFAULT_FPS = 30
FLUSH_EVERY_N_FRAMES = 30


class DatasetSpec(NamedTuple):
    path: str
    dtype: np.dtype  # type: ignore[type-arg]
    shape_per_frame: tuple[int, ...]  # shape excluding time axis


def build_dataset_specs(
    camera_names: tuple[str, ...] = CAMERA_NAMES,
    frame_shape: tuple[int, int, int] = DEFAULT_FRAME_SHAPE,
) -> list[DatasetSpec]:
    specs: list[DatasetSpec] = [
        DatasetSpec(DS_TIMESTAMP, np.dtype("float64"), ()),
        DatasetSpec(DS_QPOS,      np.dtype("float32"), (NUM_JOINTS,)),
        DatasetSpec(DS_QVEL,      np.dtype("float32"), (NUM_JOINTS,)),
        DatasetSpec(DS_TORQUE,    np.dtype("float32"), (NUM_JOINTS,)),
        DatasetSpec(DS_ACTION,    np.dtype("float32"), (NUM_JOINTS,)),
    ]
    for cam in camera_names:
        specs.append(DatasetSpec(ds_image(cam), np.dtype("uint8"), frame_shape))
    return specs
