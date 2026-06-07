# Episode Schema

## HDF5 (capture-time format)

File: `data/raw/episode_<uuid8>.hdf5`

### Datasets

| Path | Shape | Dtype | Description |
|------|-------|-------|-------------|
| `/timestamp` | `(T,)` | float64 | `time.monotonic()` seconds |
| `/observations/qpos` | `(T, 8)` | float32 | Joint positions, rad |
| `/observations/qvel` | `(T, 8)` | float32 | Joint velocities, rad/s |
| `/observations/torque` | `(T, 8)` | float32 | Joint torques, Nm |
| `/observations/images/cam_left_wrist` | `(T, 480, 640, 3)` | uint8 | BGR |
| `/observations/images/cam_right_wrist` | `(T, 480, 640, 3)` | uint8 | BGR |
| `/observations/images/cam_ceiling` | `(T, 480, 640, 3)` | uint8 | BGR |
| `/observations/images/cam_zed_left` | `(T, 480, 640, 3)` | uint8 | BGR |
| `/action` | `(T, 8)` | float32 | Commanded (leader) position, rad |

Joint order: `[joint_1, joint_2, joint_3, joint_4, joint_5, joint_6, joint_7, gripper]`

### Root Attributes

| Key | Type | Description |
|-----|------|-------------|
| `task` | str | Task string, e.g. "pick and place — red cube" |
| `fps` | int | Recording frame rate |
| `robot_type` | str | `"openarm_2.0"` |
| `is_failure` | bool | Operator-marked failure flag |
| `created_at` | str | ISO 8601 UTC wall-clock timestamp |
| `sync_tol_ms` | float | Worst-case achieved sync tolerance (ms) |
| `sync_method` | str | e.g. `"nearest_neighbour_host_ts"` |

### Pre-allocation Strategy

Datasets are pre-allocated with `maxshape=(None, ...)` and extended in blocks of 256
via `h5py.Dataset.resize()`. After episode stop, datasets are trimmed to actual length.
`f.flush()` called every 30 frames; `os.fsync()` on stop for crash safety.

## LeRobot v2 Export Format

```
data/lerobot/
  meta/
    info.json                    # fps, total_episodes, total_frames, robot_type
    tasks.jsonl                  # {"task_index": 0, "task": "..."}
    episodes/
      stats.jsonl                # per-episode: episode_index, length, fps, task
  data/chunk-000/
    episode_000000.parquet       # joint states + actions + timestamps
    episode_000001.parquet
    ...
  videos/chunk-000/
    observation.images.cam_left_wrist/episode_000000.mp4
    observation.images.cam_right_wrist/episode_000000.mp4
    observation.images.cam_ceiling/episode_000000.mp4
    observation.images.cam_zed_left/episode_000000.mp4
```

### Parquet Columns

| Column | Type | Description |
|--------|------|-------------|
| `observation.state` | list<float32>[8] | Joint positions |
| `action` | list<float32>[8] | Commanded positions |
| `timestamp` | float64 | Seconds from episode start |
| `episode_index` | int32 | Episode number |
| `frame_index` | int32 | Frame within episode |
| `next.done` | bool | True on last frame |
| `task_index` | int32 | Index into tasks.jsonl |

### LeRobot v2 vs v3

Default export is **v2** (one Parquet per episode). v3 packs multiple episodes per file.
Check your policy trainer's expectation before exporting.
