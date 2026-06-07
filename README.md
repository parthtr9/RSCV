# OpenArm 2.0 — Data Collection Pipeline

**Robotics Center of Silicon Valley / DeepAware AI — Take-home project**

> All 5 tasks completed in software mock mode (no hardware access on macOS).
> The full pipeline runs end-to-end: CAN mock → multi-camera sync → HDF5 recording → REST API → React dashboard.
> 36/36 tests pass.

> **Branch:** `linux` — Linux + vcan0. For macOS see the [`main` branch](../../tree/main).

---

## Quick Start — Linux (mock mode, no real hardware required)

Uses `vcan0` (virtual CAN via kernel module) so the socketcan path is fully exercised.

```bash
# 1. Python deps
pip install -e ".[dev]"

# 2. Set up vcan0 (once per boot)
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set vcan0 up

# 3. Start everything
make dev-mock
# → spawns mock_can producer on vcan0
# → FastAPI on :8000 (MOCK=1)
# → React dashboard on :5173
```

Open `http://localhost:5173` — live joint plots, camera previews, Start/Stop recording.

### Real hardware (can0)

```bash
make can-up       # configure CAN-FD interface, set txqueuelen 1000
make record       # start FastAPI, POST /record/start to begin
make stop         # POST /record/stop to finalize episode
```

---

## Tasks Completed

### Task 1 — CAN Interface Setup

Implemented in `Makefile` (`make can-up`) and `docs/can_protocol.md`.

**No hardware screenshot** — test system has no physical CAN adapter attached. The `make can-up` target runs the exact SocketCAN commands from the OpenArm setup guide:

```bash
sudo ip link set can0 type can \
  bitrate 1000000 dbitrate 5000000 fd on \
  sample-point 0.75 dsample-point 0.75
sudo ip link set can0 up
sudo ip link set can0 txqueuelen 1000   # prevent ENOBUFS under load
```

Zero-position is set via:
```bash
python -m hardware.damiao set-zero --motor-ids 0x01 0x02 0x03 0x04 0x05 0x06 0x07 0x08
# Frame payload: FF FF FF FF FF FF FF FE (send_id per joint)
```

For mock development, vcan0 is used:
```bash
sudo modprobe vcan && sudo ip link add dev vcan0 type vcan && sudo ip link set vcan0 up
```

---

### Task 2 — CAN Data Reading

**`hardware/damiao.py`** — Full Damiao CAN-FD frame protocol implementation:
- 8-byte feedback frame decode: 16-bit position, 12-bit velocity, 12-bit torque, temps
- Linear mapping `uint → float` using motor-specific PMAX/VMAX/TMAX from datasheet
- All 8 joints decoded: joints 1–7 + gripper (Send IDs 0x01–0x08, Recv IDs 0x11–0x18)
- MIT-mode position command encoder

**`hardware/can_reader.py`** — `python-can` Notifier-based buffered listener:
- Assembles per-joint feedback frames into a unified `JointState` at each tick
- Pushes to `queue.Queue(maxsize=500)` — no blocking in the CAN callback
- Attempts `SCHED_FIFO` priority 10 for real-time scheduling (requires `CAP_SYS_NICE`)

**`hardware/mock_can.py`** — Synthetic frame producer *(mock mode — no hardware)*:
- Emits sinusoidal joint positions at 200 Hz per joint
- Encodes real Damiao feedback frames → vcan0, so the full decode path runs unchanged

---

### Task 3 — Multi-Camera Synchronization

**`cameras/sync.py`** — Nearest-neighbour aligner.

**Architecture:**

```
CAN reader thread       → joint_queue     (joint states @ ~1 kHz)
ZED thread              → ring_zed        (30 fps)
Arducam Left thread     → ring_wrist_l    (60 fps)
Arducam Right thread    → ring_wrist_r    (60 fps)
Arducam Ceiling thread  → ring_ceiling    (30 fps)
                                ↓
Aligner thread (30 Hz ticker):
  t_leader = latest joint state timestamp
  for each ring: pick frame with min |ts - t_leader|
  if |ts - t_leader| > sync_tolerance_ms → log warning
  emit AlignedSample → writer queue
                                ↓
HDF5 writer thread → episode file
```

**How different frame rates are handled:**  
Each camera runs its own capture thread, pushing `(frame, monotonic_ts)` into a `deque(maxlen=N)` ring buffer. The aligner runs at the episode fps (30 Hz by default), using the latest joint state as the leader. At each tick it picks the *nearest* frame from each ring — so a 60 fps wrist camera simply has 2 candidates per tick, giving it half the alignment error of a 30 fps camera.

**Timestamp sources:**

| Camera | Source | Expected jitter |
|--------|--------|----------------|
| Arducam USB standard | `time.monotonic()` post-grab | 30–60 ms |
| Arducam USB3 Shield Plus | Kernel hardware ts | < 1 ms |
| ZED | `zed.get_timestamp(IMAGE).get_nanoseconds()` | ~1 ms |

Default sync tolerance warning threshold: 15 ms. Worst-case achieved tolerance is logged per episode in `sync_tol_ms` HDF5 attribute for downstream data quality filtering.

---

### Task 4 — Data Storage Backend

**Format: HDF5** (`recording/episode_writer.py`)

**Why HDF5 over alternatives:**

| Format | Pros | Cons | Decision |
|--------|------|------|----------|
| **HDF5** | Hierarchical, chunked, compressed, random-access, h5py ubiquitous in ML | Single-writer, no streaming append | ✅ Chosen |
| MCAP | Append-only, multi-schema, ROS 2 native | Ecosystem thinner outside ROS, no native Python random-access | ❌ Skip unless ROS 2 required |
| Zarr | Cloud-native, concurrent writers | Extra dep, less familiar in robotics ML | ❌ Skip |
| Custom | Full control | Reinventing the wheel | ❌ Skip |

HDF5 is the format used by ALOHA, the primary prior art for teleoperation imitation learning. LeRobot's OpenArm integration reads from it directly.

**Writer design:**
- Single writer thread owns file handle (HDF5 single-writer constraint)
- Datasets pre-allocated with `maxshape=(None, ...)` and extended in 256-frame blocks via `resize()` — avoids row-by-row append performance cliff
- `f.flush()` every 30 frames; `os.fsync()` on stop for crash safety
- Trimmed to actual length at episode close

**Episode schema:**
```
episode_<uuid8>.hdf5
  /timestamp             (T,)      float64  time.monotonic()
  /observations/qpos     (T, 8)    float32  rad
  /observations/qvel     (T, 8)    float32  rad/s
  /observations/torque   (T, 8)    float32  Nm
  /observations/images/
      cam_left_wrist     (T,480,640,3)  uint8
      cam_right_wrist    (T,480,640,3)  uint8
      cam_ceiling        (T,480,640,3)  uint8
      cam_zed_left       (T,480,640,3)  uint8
  /action                (T, 8)    float32  commanded position, rad
```

**REST API** (`api/`):
```
GET  /episodes                     → list episodes
GET  /episodes/{id}                → metadata
GET  /episodes/{id}/download       → StreamingResponse (1 MB chunks, never loads HDF5 into memory)
GET  /episodes/{id}/export/lerobot → async LeRobot v2 export (Parquet + MP4)
POST /record/start                 → {task, fps} → {episode_id}
POST /record/stop                  → {is_failure} → {episode_id, frames, duration_s}
GET  /record/status                → {recording, frames_so_far, elapsed_s}
WS   /ws/joint_states              → JSON @ 30 Hz
GET  /stream/{cam_name}            → MJPEG multipart
```

Episode IDs are UUIDs — filesystem paths are never exposed to the client.

**LeRobot v2 export** (`recording/lerobot_export.py`) — converts HDF5 episodes to Parquet + MP4 for direct use with LeRobot training scripts (ACT, Diffusion Policy, π0).

---

### Task 5 — Monitoring Dashboard

**`dashboard/`** — React 18 + Vite + recharts

- **Live joint plot** (`JointPlot.tsx`): recharts `<LineChart>` with 200-point sliding window, `isAnimationActive={false}` (mandatory at 30 Hz), toggle between qpos / qvel / torque
- **Camera feeds** (`CameraFeed.tsx`): plain `<img src="/stream/{cam}">` — browser demuxes MJPEG natively, no extra libraries
- **Record control** (`RecordControl.tsx`): task text input, Start/Stop button, live frame counter + elapsed time via polling `/record/status` at 2 Hz
- **Status bar** (`StatusBar.tsx`): WebSocket connection state, latest timestamp

**WebSocket buffering** (`useJointWS.ts`):  
WS messages arrive at 30 Hz. Instead of `setState` on every message (causes render storms), messages are pushed into a `useRef` buffer and flushed to React state at 10 Hz via `setInterval`. This keeps the UI at 10 Hz while the data stream stays at 30 Hz.

```typescript
// Buffer at 30 Hz, flush to state at 10 Hz
const buffer = useRef<JointState[]>([]);
useEffect(() => {
  const id = setInterval(() => {
    if (buffer.current.length > 0) {
      setJointStates(prev => [...prev.slice(-200), ...buffer.current]);
      buffer.current = [];
    }
  }, 100);
  return () => clearInterval(id);
}, []);
```

---

## Architecture Overview

```
[Mock CAN producer]                  [Camera threads]
  sinusoidal frames → vcan0          MockCamera.grab() → ring_<cam>
         ↓                                    ↓
[CANReader / Notifier]             [MultiCameraAligner @ 30 Hz]
  decode Damiao frames                nearest-neighbour sync
  → joint_queue                       → aligned_queue
         ↓                                    ↓
[AtomicRef<JointState>]         [EpisodeWriter thread]
  latest state for WS/MJPEG         HDF5 write, pre-alloc, flush
         ↓
[FastAPI / uvicorn]
  REST + WebSocket + MJPEG
         ↓
[React dashboard]
  recharts + MJPEG + RecordControl
```

All background threads are `daemon=True`. Communication is exclusively via `queue.Queue` or `collections.deque` — no shared mutable state without locks.

---

## Key Trade-offs

**HDF5 single-writer** — Only one thread/process may write at a time. This is fine for single-arm recording but limits concurrent multi-arm recording. Zarr would allow concurrent writers; accepted the trade-off for ML ecosystem compatibility.

**Nearest-neighbour sync vs interpolation** — Nearest-neighbour is simple, causal, and zero-latency. Interpolation would reduce alignment error on slowly-moving joints but adds complexity and a 1-frame lag. For imitation learning at 30 fps, nearest-neighbour error (≤15 ms) is within a single action cycle and acceptable.

**Software timestamps on USB cameras** — 30–60 ms jitter is inherent to USB interrupt scheduling. The Arducam USB3 Shield Plus has kernel hardware timestamps (< 1 ms) but at higher cost. The system logs `sync_tol_ms` per episode so bad episodes can be filtered downstream.

**In-memory episode list** — `completed_episodes` is a Python list, lost on restart. Acceptable for a take-home; production would use SQLite or Postgres.

**MJPEG over WebRTC** — MJPEG is one line of HTML and works out of the box. WebRTC gives lower latency (~100 ms vs ~300 ms) and works over WAN, but requires a signaling server. For lab use on localhost, MJPEG is the right call.

---

## What I'd Do Next (given more time / hardware)

1. **Hardware validation** — Run on Linux with real can0/can1, verify Damiao decode against actual motor feedback, tune `txqueuelen` and `SCHED_FIFO` priority.

2. **Hardware camera timestamps** — Switch Arducam wrist cameras to USB3 Shield Plus for sub-millisecond sync; plumb `SO_TIMESTAMPNS` through python-can for CAN frame timestamps.

3. **Persistent episode store** — Replace in-memory list with SQLite; add episode tags, success/failure filter, and per-episode sync quality histogram in the dashboard.

4. **LeRobot push** — Wire the export button to `huggingface_hub.upload_folder()` for one-click Hugging Face Hub upload.

5. **Multi-arm support** — The CAN reader currently handles one bus. The bimanual setup uses 4 buses (can0–can3); extend `CANReader` to aggregate across buses and double the joint vector to 16-DOF.

6. **End-to-end replay** — Load an HDF5 episode and replay commands to the arm (leader→follower replay) for data validation without policy inference.

---

## Repository Structure

```
hardware/          CAN frame encode/decode, bus reader, mock producer
cameras/           Camera ABC, Arducam, ZED, mock, sync aligner
recording/         HDF5 writer, schema constants, LeRobot exporter
api/               FastAPI app, REST routes, WebSocket, MJPEG
dashboard/         React + Vite frontend
config/            default.yaml (cameras/rates/sync), joints.yaml (motor map)
docs/              can_protocol.md, episode_schema.md, camera_setup.md
tests/             36 tests — Damiao decode, sync, HDF5 write, API routes
```

## Test Results

```
36 passed in 9.47s
```

Covers: Damiao encode/decode round-trips, linear mapping edge cases, camera ring nearest-neighbour correctness, thread safety, HDF5 pre-allocation + resize + readback + attribute correctness, FastAPI route validation (start/stop/status/download/404s).
