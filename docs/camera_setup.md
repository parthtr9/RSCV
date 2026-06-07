# Camera Setup

## Camera Identification — CRITICAL

**Never use `/dev/video*` index** — USB enumeration order changes across reboots.
Always identify by `ID_SERIAL_SHORT` via udev.

### Find serial IDs

```bash
for f in /dev/video*; do
  udevadm info -a -n "$f" | grep -E 'KERNEL|ID_SERIAL_SHORT' | head -2
  echo "---"
done
```

### udev Rules (persistent symlinks)

Create `/etc/udev/rules.d/99-openarm-cameras.rules`:

```
SUBSYSTEM=="video4linux", ATTR{index}=="0", \
  ENV{ID_SERIAL_SHORT}=="ArducamWristLeft_001", \
  SYMLINK+="arducam_left_wrist"

SUBSYSTEM=="video4linux", ATTR{index}=="0", \
  ENV{ID_SERIAL_SHORT}=="ArducamWristRight_002", \
  SYMLINK+="arducam_right_wrist"

SUBSYSTEM=="video4linux", ATTR{index}=="0", \
  ENV{ID_SERIAL_SHORT}=="ArducamCeiling_003", \
  SYMLINK+="arducam_ceiling"
```

Reload: `sudo udevadm control --reload && sudo udevadm trigger`

## Timestamping

| Camera | Source | Expected jitter |
|--------|--------|-----------------|
| Arducam USB standard | `time.monotonic()` post-grab | 30–60 ms |
| Arducam USB3 Shield Plus | Kernel hardware timestamp | < 1 ms |
| ZED | `zed.get_timestamp(IMAGE).get_nanoseconds()` | ~1 ms |

Record `sync_method` in episode attrs for traceability.

## ZED SDK Installation

pyzed is **not on PyPI**. Install from the ZED SDK installer:

```bash
# 1. Download SDK from stereolabs.com
# 2. Run installer (sets up /usr/local/zed)
chmod +x ZED_SDK_Ubuntu22_cuda12.x_v*.run
./ZED_SDK_Ubuntu22_cuda12.x_v*.run

# 3. Install pyzed Python bindings
python /usr/local/zed/get_python_api.py

# Verify
python -c "import pyzed.sl as sl; print(sl.__version__)"
```

ZED grab is blocking — run one thread per ZED, never from asyncio.

## Multi-Camera Sync

Architecture: nearest-neighbour, joint state as leader at `fps` Hz.
See `cameras/sync.py:MultiCameraAligner`.

- `sync_tolerance_ms: 15` default (warning threshold)
- Expect 30–60 ms on software USB timestamps (acceptable for imitation learning)
- Hardware timestamps (Arducam Shield Plus) achieve < 1 ms
- Log `sync_tol_ms` per episode and surface in dashboard

## Arducam OpenCV on Linux

Install V4L2 backend:
```bash
sudo apt install v4l-utils v4l2loopback-dkms
```

Set resolution before first read — do not rely on defaults:
```python
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 60)
```

## MJPEG Preview Encoding

```python
ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
```

Quality 70 balances bandwidth vs latency on localhost. Uncompressed frames
at 30+ fps saturate even loopback. Do not raise quality above 85 for preview.
