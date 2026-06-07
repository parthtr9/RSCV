# CLAUDE.md — OpenArm 2.0 Data Collection Pipeline

> **Project**: Teleoperation data collection platform for OpenArm 2.0 (7-DOF, Damiao motors,
> CAN-FD) with 4 cameras (2× wrist Arducam, 1× ceiling Arducam, 1× ZED stereo).
> Produces synchronized joint-state + multi-camera episodes in LeRobot / HDF5 format
> for downstream imitation learning (ACT, Diffusion Policy, π0).
>
> **Platform**: Linux only. The USB-CAN adapter has no macOS or Windows drivers.
> The ZED SDK is also Linux/Windows only — use mock mode on macOS.

---

## Repository Structure

```
openarm_datacollection/
├── CLAUDE.md                  ← you are here
├── README.md
├── Makefile                   ← canonical entry points (see Commands below)
├── pyproject.toml             ← single source of truth for deps + tool config
│
├── hardware/
│   ├── __init__.py
│   ├── damiao.py              ← CAN frame encode/decode, motor constants, joint map
│   ├── can_reader.py          ← python-can FD Bus wrapper, asyncio-safe listener
│   └── mock_can.py            ← vcan0 synthetic frame producer (sinusoidal joints)
│
├── cameras/
│   ├── __init__.py
│   ├── base.py                ← CameraSource ABC: grab() -> (frame: ndarray, mono_ts: float)
│   ├── zed_camera.py          ← pyzed.sl wrapper (LEFT + DEPTH retrieval)
│   ├── arducam_camera.py      ← cv2.VideoCapture + pyudev serial-ID resolution
│   ├── mock_camera.py         ← synthetic timestamped frames (no hardware)
│   └── sync.py                ← ring buffers + nearest-neighbour multi-camera aligner
│
├── recording/
│   ├── __init__.py
│   ├── episode_writer.py      ← HDF5 episode writer (capture-time, single-writer thread)
│   ├── lerobot_export.py      ← HDF5 → LeRobot v2 Parquet + MP4 converter
│   └── schema.py              ← episode schema constants (dataset keys, dtypes, shapes)
│
├── api/
│   ├── __init__.py
│   ├── main.py                ← FastAPI app factory + lifespan context
│   ├── routes_episodes.py     ← GET /episodes, GET /episodes/{id}, GET /episodes/{id}/download
│   ├── routes_record.py       ← POST /record/start, POST /record/stop, GET /record/status
│   ├── ws.py                  ← WS /ws/joint_states (30 Hz JSON) + MJPEG /stream/{cam}
│   └── deps.py                ← shared FastAPI dependencies (recorder singleton, state bus)
│
├── dashboard/                 ← React + Vite frontend
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       ├── components/
│       │   ├── JointPlot.tsx  ← recharts live joint-angle strip chart
│       │   ├── CameraFeed.tsx ← MJPEG <img> tag per camera
│       │   ├── RecordControl.tsx ← Start/Stop button + episode counter
│       │   └── StatusBar.tsx
│       └── hooks/
│           └── useJointWS.ts  ← react-use-websocket with message buffering
│
├── config/
│   ├── default.yaml           ← camera indices/serials, rates, sync tolerance
│   └── joints.yaml            ← per-joint motor type, send_id, recv_id, limits
│
├── docs/
│   ├── can_protocol.md        ← Damiao frame layout, system commands reference
│   ├── episode_schema.md      ← HDF5 + LeRobot schema with field descriptions
│   └── camera_setup.md        ← udev rules, serial IDs, ZED firmware notes
│
└── tests/
    ├── test_damiao.py          ← round-trip encode/decode, edge cases
    ├── test_sync.py            ← nearest-neighbour aligner correctness
    ├── test_episode_writer.py  ← HDF5 write + readback
    └── test_api.py             ← FastAPI routes (httpx AsyncClient)
```

---

## Commands

```bash
# --- Setup ---
pip install -e ".[dev]"               # install package + dev extras
cd dashboard && npm install           # install frontend deps

# --- Mock mode (no hardware required) ---
make dev-mock                         # full stack: vcan0 + synthetic cameras + API + dashboard
# Equivalent to:
python -m hardware.mock_can &         # synthetic CAN frames → vcan0
uvicorn api.main:app --reload &       # FastAPI on :8000
cd dashboard && npm run dev           # Vite on :5173 (proxies /api + /ws to :8000)

# --- Real hardware ---
make can-up                           # bring up can0 + can1 CAN-FD
make record                           # start recording session
make stop                             # stop + finalize episode

# --- Testing ---
pytest                                # run all tests
pytest tests/test_damiao.py -v        # single module
pytest --cov=openarm_datacollection   # with coverage

# --- Linting / formatting ---
ruff check . && ruff format .         # must pass before committing
mypy openarm_datacollection           # type-check (strict mode)

# --- Export ---
python -m recording.lerobot_export \
  --input data/raw/ \
  --output data/lerobot/ \
  --task "pick and place"
```

---

## CAN-FD Interface Setup

### Bring up interfaces (run once per boot, or add to systemd)

```bash
# Single arm
sudo ip link set can0 type can \
  bitrate 1000000 dbitrate 5000000 fd on sample-point 0.75 dsample-point 0.75
sudo ip link set can0 up
sudo ip link set can0 txqueuelen 1000          # prevent ENOBUFS under load

# Or using the OpenArm helper:
openarm-can-configure-socketcan can0 -fd -b 1000000 -d 5000000

# Bimanual (4-bus setup):
openarm-can-configure-socketcan-4-arms -fd

# Verify UP:
ip -details link show can0                     # look for "UP" and "fd on"
candump can0 -L                                # confirm frames arriving
```

### Mock CAN (vcan0, no hardware)

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set vcan0 up
# Then run: python -m hardware.mock_can --interface vcan0
```

### Zero position

```bash
# Via LeRobot (recommended — handles all joints safely):
lerobot-calibrate --robot-type=openarm

# Via raw Damiao frame (joint 1, motor 0x01):
# Send: arbitration_id=0x01, data=FF FF FF FF FF FF FF FE, fd=True
python -m hardware.damiao set-zero --motor-ids 0x01 0x02 0x03 0x04 0x05 0x06 0x07 0x08
```

---

## Joint / Motor / CAN-ID Map

This is the ground truth for `hardware/damiao.py` and `config/joints.yaml`.
**Do not hardcode these elsewhere** — always import from `hardware.damiao.JOINT_MAP`.

| Joint | Motor Type | Send ID | Recv ID | Notes |
|-------|------------|---------|---------|-------|
| joint_1 | DM8009(P) | `0x01` | `0x11` | High-torque shoulder |
| joint_2 | DM8009(P) | `0x02` | `0x12` | High-torque shoulder |
| joint_3 | DM4340 | `0x03` | `0x13` | Elbow |
| joint_4 | DM4340P | `0x04` | `0x14` | Elbow |
| joint_5 | DM4310 | `0x05` | `0x15` | Wrist |
| joint_6 | DM4310 | `0x06` | `0x16` | Wrist |
| joint_7 | DM4310 | `0x07` | `0x17` | Wrist |
| gripper | DM4310 | `0x08` | `0x18` | Gripper |

**Recv ID = Send ID + 0x10** — always.

---

## Damiao CAN Frame Protocol

### Feedback frame (recv_id, e.g. 0x11)

```
Byte  0:    [7:4] status  |  [3:0] motor_id
Bytes 1-2:  pos_u    (16-bit unsigned)
Byte  3 + high nibble of 4:  vel_u  (12-bit)
Low nibble of 4 + Byte 5:    torq_u (12-bit)
Byte  6:    T_mos (motor temp, °C)
Byte  7:    T_rotor (rotor temp, °C)
```

### Decode (linear mapping)

```python
# N=16 for position, N=12 for velocity and torque
value = x_min + (u / (2**N - 1)) * (x_max - x_min)
```

**PMAX/VMAX/TMAX must be read from `dm_motor_constants.hpp` — never hardcode guesses.**
Position range is ±12.5 rad across all Damiao motors; velocity/torque limits vary by model.

### System command frames (send_id, e.g. 0x01)

```
Enable motor:       FF FF FF FF FF FF FF FC
Disable motor:      FF FF FF FF FF FF FF FD
Set zero position:  FF FF FF FF FF FF FF FE
Clear error:        FF FF FF FF FF FF FF FB
```

All use `is_fd=True, bitrate_switch=True` on the `can.Message`.

---

## Episode Schema

### HDF5 (capture-time format — single writer)

```
episode_XXXXXX.hdf5
  /timestamp                  (T,)       float64   monotonic seconds (time.monotonic())
  /observations/
      qpos                    (T, 8)     float32   joint positions, radians
      qvel                    (T, 8)     float32   joint velocities, rad/s
      torque                  (T, 8)     float32   joint torques, Nm
      images/
          cam_left_wrist      (T,H,W,3)  uint8     480×640 default
          cam_right_wrist     (T,H,W,3)  uint8
          cam_ceiling         (T,H,W,3)  uint8
          cam_zed_left        (T,H,W,3)  uint8
  /action                     (T, 8)     float32   commanded (leader) position, radians

Attributes (root):
  task            str      e.g. "pick and place — red cube"
  fps             int      recording frame rate
  robot_type      str      "openarm_2.0"
  is_failure      bool     operator-marked
  created_at      str      ISO 8601 UTC
  sync_tol_ms     float    achieved worst-case sync tolerance this episode
```

### LeRobot export (ML-ready format)

```
data/lerobot/
  meta/
    info.json                 # fps, shapes, dataset stats
    tasks.jsonl               # task strings
    episodes/stats.jsonl      # per-episode length, success, task_index
  data/chunk-000/
    episode_*.parquet         # joint states + actions + timestamps
  videos/chunk-000/
    observation.images.cam_left_wrist/episode_*.mp4
    observation.images.cam_right_wrist/episode_*.mp4
    observation.images.cam_ceiling/episode_*.mp4
    observation.images.cam_zed_left/episode_*.mp4
```

LeRobot column names: `observation.state` (8-DOF pos), `action` (8-DOF commanded),
`observation.images.<cam>`, `timestamp`, `episode_index`, `frame_index`, `next.done`.

---

## Camera Architecture

### Camera identification

**Always identify USB cameras by serial, never by `/dev/video*` index** — USB enumeration
order is non-deterministic across reboots.

```python
# cameras/arducam_camera.py
import pyudev
context = pyudev.Context()
for device in context.list_devices(subsystem='video4linux'):
    serial = device.get('ID_SERIAL_SHORT')   # e.g. "ArducamWristLeft_001"
    devnode = device.device_node             # /dev/video4
```

Map serials to logical names in `config/default.yaml`:
```yaml
cameras:
  cam_left_wrist:  serial: "ArducamWristLeft_001"
  cam_right_wrist: serial: "ArducamWristRight_002"
  cam_ceiling:     serial: "ArducamCeiling_003"
  cam_zed:         serial: null   # ZED SDK handles identification
```

### Timestamping

| Camera | Timestamp source | Expected jitter |
|--------|-----------------|-----------------|
| Arducam USB (standard) | Host `time.monotonic()` post-grab | 30–60 ms |
| Arducam USB3 Shield Plus | Hardware timestamp (kernel driver) | < 1 ms |
| ZED stereo | `zed.get_timestamp(sl.TIME_REFERENCE.IMAGE)` nanoseconds | ~1 ms |

Always record the timestamp source in episode attrs (`sync_method`).

### Multi-camera alignment (nearest-neighbour)

```
  CAN reader thread    → queue_joint  (joint states @ ~1 kHz)
  ZED thread           → ring_zed     (frames @ 30 fps)
  Arducam L thread     → ring_wrist_l (frames @ 60 fps)
  Arducam R thread     → ring_wrist_r (frames @ 60 fps)
  Arducam ceil thread  → ring_ceiling (frames @ 30 fps)
                                      ↓
  Aligner thread (leader = joint state):
    at each tick (1/fps):
      t_leader = latest joint state timestamp
      for each ring_<cam>: pick frame with min |ts - t_leader|
      if any |ts - t_leader| > sync_tolerance_ms → log warning, mark frame
      emit aligned sample → writer queue
                                      ↓
  Writer thread → HDF5 episode file (preallocated datasets, flush every N frames)
```

Default `sync_tolerance_ms: 15` (warn). Expect 30–60 ms on software USB sync;
record the worst-case achieved tolerance per episode for data quality tracking.

---

## API Design

### REST endpoints

```
GET  /episodes                     → list of episode metadata (id, task, fps, length, created_at)
GET  /episodes/{id}                → full metadata + per-camera frame count
GET  /episodes/{id}/download       → StreamingResponse (HDF5 file, 1 MB chunks)
GET  /episodes/{id}/export/lerobot → trigger async LeRobot export, return job_id
GET  /export/{job_id}/status       → export job status

POST /record/start                 → {task: str, fps: int} → {episode_id: str}
POST /record/stop                  → {} → {episode_id: str, frames: int, duration_s: float}
GET  /record/status                → {recording: bool, episode_id, frames_so_far, elapsed_s}

WS   /ws/joint_states              → push JSON @ 30 Hz: {ts, qpos[8], qvel[8], torque[8]}
GET  /stream/{cam_name}            → MJPEG multipart/x-mixed-replace (camera preview)
```

### Conventions

- **Episode IDs** are UUIDs (not filenames). Never accept filesystem paths as input.
- **Large file downloads** use `FileResponse` or `StreamingResponse` with chunked generator —
  never load an entire HDF5 into memory.
- **Background tasks**: use FastAPI `BackgroundTasks` or `asyncio.create_task` for export jobs.
- **Error responses**: always return `{"detail": "human-readable message"}` with a meaningful
  HTTP status code. Never expose raw exception tracebacks in production.
- **CORS**: allow `localhost:5173` in dev mode only. Do not allow wildcard in production.

---

## Dashboard (React)

### WebSocket message buffering — CRITICAL

**Never call `setState` directly on every incoming WS message** — at 30 Hz this causes
render storms and UI jank. Instead:

```typescript
// hooks/useJointWS.ts
const buffer = useRef<JointState[]>([]);
const { lastMessage } = useWebSocket(WS_URL);

useEffect(() => {
  if (lastMessage) buffer.current.push(JSON.parse(lastMessage.data));
}, [lastMessage]);

// Flush to state at display rate (e.g. 10 Hz or rAF)
useEffect(() => {
  const id = setInterval(() => {
    if (buffer.current.length > 0) {
      setJointStates(prev => [...prev.slice(-200), ...buffer.current]);
      buffer.current = [];
    }
  }, 100);  // flush every 100 ms
  return () => clearInterval(id);
}, []);
```

### Camera preview

```tsx
// components/CameraFeed.tsx — MJPEG via plain <img>, browser handles demux
<img
  src={`/stream/${camName}`}
  style={{ width: '100%' }}
  alt={camName}
/>
```

No additional libraries needed for MJPEG. For lower latency, swap to WebRTC
(see `docs/camera_setup.md`).

### Joint strip chart

Use recharts `<LineChart>` with a 200-point sliding window. Render each of the 8 joints
as a separate `<Line>` with `isAnimationActive={false}` (mandatory for 30 Hz data).

---

## Threading Model

```
[Main process]
  ├── CAN listener thread (SCHED_FIFO priority 10)
  │     python-can Notifier → joint_queue (maxsize=500)
  │
  ├── ZED capture thread
  │     zed.grab() → ring_zed (deque, maxlen=60)
  │
  ├── Arducam Left thread
  │     cap.read() → ring_wrist_l (deque, maxlen=120)
  │
  ├── Arducam Right thread
  │     cap.read() → ring_wrist_r
  │
  ├── Arducam Ceiling thread
  │     cap.read() → ring_ceiling
  │
  ├── Aligner + record thread (30 Hz ticker)
  │     reads queues/rings → aligned_queue (maxsize=10)
  │
  ├── HDF5 writer thread
  │     drains aligned_queue → episode_XXXXXX.hdf5
  │
  └── FastAPI / uvicorn (asyncio event loop)
        reads latest joint state from shared AtomicRef for /ws + /stream
```

Use `threading.Thread(daemon=True)` for all background threads.
Communicate exclusively via `queue.Queue` or `collections.deque` — never shared mutable state
without locks.

---

## Mock-First Development Workflow

Every module must run under `--mock` with no hardware. This is non-negotiable.

```python
# hardware/can_reader.py
def create_bus(mock: bool = False) -> can.BusABC:
    if mock:
        return can.Bus(interface='virtual', channel='vcan0')
    return can.Bus(interface='socketcan', channel='can0', fd=True)

# cameras/base.py
def create_cameras(config: Config, mock: bool = False) -> dict[str, CameraSource]:
    cls = MockCamera if mock else resolve_camera_class(config)
    ...
```

`make dev-mock` sets `MOCK=1` env var; all factory functions check it.

The mock CAN producer (`hardware/mock_can.py`) emits synthetic Damiao feedback frames
with sinusoidal joint positions so the full decode → sync → write → API → dashboard
pipeline can be validated on a laptop.

---

## Code Style & Conventions

- **Python 3.11+**, type hints everywhere, `from __future__ import annotations`.
- **ruff** for lint + format (line length 100). Config in `pyproject.toml`.
- **mypy strict** — no `# type: ignore` without a comment explaining why.
- **No print statements** in library code — use `logging.getLogger(__name__)`.
- All hardware-interfacing code goes under `hardware/` or `cameras/`; never import
  `can` or `pyzed` directly from `api/` or `recording/`.
- Use `pathlib.Path` everywhere — never `os.path.join`.
- Timestamps are always **`time.monotonic()`** internally. Convert to wall clock
  only at episode write time for the `created_at` attribute.

---

## Gotchas & Known Issues

### CAN / Hardware

- **Linux-only.** CAN USB adapter (typically gs_usb or Peak) has no macOS driver.
  Always use `--mock` on non-Linux hosts.
- **openarm_can Python bindings are officially UNSTABLE** ("will change DRASTICALLY").
  Wrap entirely behind `hardware/can_reader.py` — never import from `openarm_can` in
  other modules. When the API breaks, only one file needs updating.
- **PMAX / VMAX / TMAX**: read from `include/openarm/damiao_motor/dm_motor_constants.hpp`
  in the enactic/openarm repo. Do not hardcode limits — the decode will silently produce
  wrong SI values if limits are wrong.
- **txqueuelen**: set to ≥1000 on the CAN interface or you will get `ENOBUFS` under load.
- **CAN dropped frames on Raspberry Pi**: known issue with python-can under CPU load.
  Always use a `Notifier`-based buffered listener; never `bus.recv()` in a tight loop.
- **Real-time scheduling**: run the CAN listener under `SCHED_FIFO` priority 10 if possible:
  `chrt -f 10 <pid>` or use `os.sched_setscheduler()` (requires `CAP_SYS_NICE`).

### Cameras

- **Never identify cameras by `/dev/video*` index** — USB enumeration is non-deterministic.
  Always use `ID_SERIAL_SHORT` via pyudev.
- **ZED SDK**: `zed.grab()` is blocking; run one thread per ZED. Do not call it from asyncio.
- **Arducam standard USB sync jitter** is 30–60 ms (software timestamps). This is expected.
  Log `sync_tol_ms` per episode and surface it in the dashboard.
- **macOS**: ZED SDK has a macOS build but pyzed Python bindings are unreliable. Use mock.

### Storage

- **HDF5 single-writer**: only one process/thread may write to an HDF5 file at a time.
  The writer thread is the sole owner of the file handle during recording.
- **Pre-allocate HDF5 datasets** with `maxshape=(None, ...)` and extend with `resize()` —
  never append row-by-row without pre-allocation (massive performance cliff).
- **Flush interval**: call `f.flush()` every 30–60 frames, not every frame.
  Call `os.fsync(f.id.get_vfd_handle())` on episode stop for crash safety.
- **LeRobot v2 vs v3**: v3 packs multiple episodes per Parquet file; v2 is one-per-episode.
  Default to v2 for compatibility. Check target policy trainer's expectation before exporting.

### API / Dashboard

- **Episode IDs are UUIDs** — never expose raw filesystem paths to the client.
- **Streaming downloads**: use `StreamingResponse` with a generator; never
  `return FileResponse(hdf5_path)` for files >100 MB (loads into memory on some ASGI servers).
- **MJPEG preview**: encode frames as JPEG (`cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])`)
  before writing to the multipart stream. Uncompressed frames will saturate localhost.
- **`isAnimationActive={false}`** on all recharts `<Line>` components —
  mandatory when data updates faster than ~2 Hz.

---

## Dependencies

```toml
# pyproject.toml (key entries)
[project]
requires-python = ">=3.11"
dependencies = [
  "python-can>=4.3",
  "h5py>=3.10",
  "numpy>=1.26",
  "opencv-python>=4.9",
  "pyudev>=0.24",
  "fastapi>=0.110",
  "uvicorn[standard]>=0.29",
  "pydantic>=2.6",
  "httpx>=0.27",        # for test client
  "pyyaml>=6.0",
]

[project.optional-dependencies]
zed = ["pyzed"]         # install separately from stereolabs.com
lerobot = ["lerobot"]   # pip install lerobot
dev = ["pytest", "pytest-asyncio", "pytest-cov", "ruff", "mypy"]
```

`pyzed` is not on PyPI — install from the ZED SDK installer script. Document this in README.
Do not add it to `dependencies` or CI will break.

---

## What Is Not in This Repo

- **Trained policies** (ACT, Diffusion Policy weights) — use LeRobot training scripts.
- **Robot URDF / simulation** — see enactic/openarm and mujoco-openarm.
- **Teleop leader-arm setup** — see OpenArm docs for leader/follower configuration.
- **Dataset hosting** — push LeRobot exports to Hugging Face Hub separately.

---

## REFERENCES.md — Mandatory Citation Log

Whenever you use an **external resource** while working on this project — a paper, library,
documentation page, GitHub repo, blog post, or tool — append an entry to `REFERENCES.md`
in the project root.

### Entry format

```markdown
## <Resource Title>
- **URL / Citation**: <url or full citation>
- **Date added**: YYYY-MM-DD
- **Contribution**: <one or two sentences: what it informed or provided>
- **Applied in**: `<file or module path(s)>`
```

### Rules

- **Append newest-first** (most recent entry at the top, below the header).
- **No duplicates** — check the file before adding. If a resource is used in a new module,
  update the existing entry's `Applied in` field instead of creating a duplicate.
- This applies to everything: SDK docs, arXiv papers, Stack Overflow answers that shaped a
  design decision, blog posts, datasheets, GitHub issues, example repos.
- If a resource is consulted but ultimately not used, do not add it.
- Run `grep "<url>"  REFERENCES.md` before adding to check for duplicates.

### Seed entries (bootstrap from project research)

The following resources were used to design this project and should be the initial content
of `REFERENCES.md` when the file is first created:

| Resource | URL |
|---|---|
| OpenArm docs | https://docs.openarm.dev |
| openarm_can library | https://github.com/enactic/openarm_can |
| LeRobot OpenArm integration | https://huggingface.co/docs/lerobot/openarm |
| Damiao DM8009 motor datasheet | https://docs.openarm.dev/assets/files/dm8009-*.pdf |
| ALOHA data collection (prior art) | https://github.com/tonyzhaozh/act |
| ZED multi-camera example | https://github.com/stereolabs/zed-multi-camera |
| python-can docs | https://python-can.readthedocs.io |
| Arducam UVC + OpenCV on Linux | https://docs.arducam.com/UVC-Camera/Appilcation-Note/OpenCV-Python-GStreamer-on-linux/ |
| Arducam hardware timestamp guide | https://docs.arducam.com/USB-Industrial-Camera/USB3.0-Camera-Shield-Plus/The-Guide-to-Hardware-Timestamp/ |
| MCAP format intro (Foxglove) | https://foxglove.dev/blog/introducing-the-mcap-file-format |

---

*Last updated: 2025-06. Verify motor constants and openarm_can API against the current
enactic/openarm repo before implementation — both are under active development.*
