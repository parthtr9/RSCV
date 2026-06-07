# REFERENCES.md
External resources used in this project, sorted newest-first. See `CLAUDE.md` for the entry format and contribution rules.

---

## Foxglove: MCAP as the ROS 2 Default Bag Format
- **URL**: https://foxglove.dev/blog/mcap-as-the-ros2-default-bag-format
- **Date added**: 2025-06-06
- **Contribution**: Confirmed that MCAP became the default rosbag2 storage format in ROS 2 Iron Irwini (May 2023), replacing SQLite3; informed the storage format trade-off analysis and the decision to recommend MCAP only for ROS 2-centric workflows.
- **Applied in**: `recording/lerobot_export.py`, `docs/episode_schema.md`

---

## Foxglove: Introducing the MCAP File Format
- **URL**: https://foxglove.dev/blog/introducing-the-mcap-file-format
- **Date added**: 2025-06-06
- **Contribution**: Explained MCAP's self-contained, append-only, multi-schema design and its ~20–50% size reduction vs SQLite3 with Zstd compression; used to evaluate MCAP vs HDF5 vs Zarr for episode storage.
- **Applied in**: `recording/episode_writer.py`, `docs/episode_schema.md`

---

## Arducam: Hardware Timestamp Guide (USB3 Camera Shield Plus)
- **URL**: https://docs.arducam.com/USB-Industrial-Camera/USB3.0-Camera-Shield-Plus/The-Guide-to-Hardware-Timestamp/
- **Date added**: 2025-06-06
- **Contribution**: Documented kernel-level hardware timestamping available on the Arducam USB3 Shield Plus, enabling sub-millisecond sync jitter vs the 30–60 ms expected from software timestamps; informed the camera sync tolerance table in `CLAUDE.md`.
- **Applied in**: `cameras/arducam_camera.py`, `cameras/sync.py`

---

## Arducam: UVC Cameras with OpenCV, Python, and GStreamer on Linux
- **URL**: https://docs.arducam.com/UVC-Camera/Appilcation-Note/OpenCV-Python-GStreamer-on-linux/
- **Date added**: 2025-06-06
- **Contribution**: Documented `cv2.VideoCapture(index, cv2.CAP_V4L2)` usage for UVC cameras on Linux; informed the capture thread design and V4L2 backend selection.
- **Applied in**: `cameras/arducam_camera.py`

---

## ALOHA 2.0 Data Collection Documentation (Trossen Robotics)
- **URL**: https://docs.trossenrobotics.com/aloha_docs/2.0/operation/data_collection.html
- **Date added**: 2025-06-06
- **Contribution**: Prior art for aligning 50 Hz joint states with 30 fps camera frames into timestamped HDF5 episodes; confirmed ≤10 ms as the target sync tolerance and documented 30–60 ms as the realistic software-only jitter figure. Informed the HDF5 episode schema (`/action`, `/observations/qpos`, `/observations/images/<cam>`).
- **Applied in**: `cameras/sync.py`, `recording/episode_writer.py`, `recording/schema.py`

---

## RoboticsCenter Developer Wiki: OpenArm SocketCAN Setup, ROS2 & Data Collection
- **URL**: https://www.roboticscenter.ai/wiki/openarm/
- **Date added**: 2025-06-06
- **Contribution**: Detailed SocketCAN bring-up commands, CAN-FD bitrate configuration, multi-bus bimanual setup (`can0`–`can3`), and data collection workflow for OpenArm; used to write the CAN setup section and Makefile targets.
- **Applied in**: `hardware/can_reader.py`, `Makefile`, `CLAUDE.md`

---

## RoboticsCenter: OpenArm 101 Setup Guide
- **URL**: https://www.roboticscenter.ai/en/hardware/openarm/setup
- **Date added**: 2025-06-06
- **Contribution**: Step-by-step CAN-FD interface setup, `txqueuelen` tuning guidance, and camera mount context; confirmed `openarm-can-configure-socketcan` CLI syntax and validated the joint/CAN-ID map.
- **Applied in**: `hardware/can_reader.py`, `CLAUDE.md`, `docs/can_protocol.md`

---

## GitHub: enactic/openarm — Camera Mount for Data Collection (Issue #307)
- **URL**: https://github.com/enactic/openarm/issues/307
- **Date added**: 2025-06-06
- **Contribution**: Confirmed that multi-camera data collection mounting is an acknowledged open issue in the official repo; informed the architecture decision to build camera setup independently of any official reference implementation.
- **Applied in**: `cameras/base.py`, `docs/camera_setup.md`

---

## OpenArm Docs: ROS2 Control
- **URL**: https://docs.openarm.dev/software/ros2/control/
- **Date added**: 2025-06-06
- **Contribution**: Documented the `openarm_ros2` hardware interface exposing position/velocity/effort and the `use_fake_hardware:=true` flag for mock development; informed the mock-first development strategy.
- **Applied in**: `hardware/mock_can.py`, `Makefile`

---

## OpenArm Docs: CAN Library
- **URL**: https://docs.openarm.dev/software/can/
- **Date added**: 2025-06-06
- **Contribution**: Documented `openarm_can` C++ library API: `init_arm_motors()`, `enable_all()`, `refresh_all()`, `recv_all(timeout_us)`, per-motor `get_position()`/`get_velocity()`/`get_torque()`; confirmed that Python bindings are officially marked UNSTABLE. Drove the decision to wrap behind `hardware/can_reader.py`.
- **Applied in**: `hardware/can_reader.py`, `hardware/damiao.py`

---

## GitHub: enactic/openarm_can
- **URL**: https://github.com/enactic/openarm_can
- **Date added**: 2025-06-06
- **Contribution**: Source of the `openarm_can` C++ library and Python bindings; provided the canonical joint→motor→CAN-ID map (Send IDs `0x01`–`0x08`, Recv IDs `0x11`–`0x18`) and confirmed the "UNSTABLE" status of Python bindings.
- **Applied in**: `hardware/can_reader.py`, `hardware/damiao.py`, `config/joints.yaml`

---

## GitHub: cmjang/DM_Motor_Control (Damiao Motor Control)
- **URL**: https://github.com/cmjang/DM_Motor_Control
- **Date added**: 2025-06-06
- **Contribution**: Open-source reference for Damiao motor CAN protocol implementation; cross-referenced frame layout (status nibble, 16-bit position, 12-bit velocity/torque packing) and system command bytes (`FC`–`FE`) against the official datasheet.
- **Applied in**: `hardware/damiao.py`, `docs/can_protocol.md`

---

## OpenArm Docs: Damiao DM8009 Motor Datasheet
- **URL**: https://docs.openarm.dev/assets/files/dm8009-90ee7f15d06666e15afd49e5d5417150.pdf
- **Date added**: 2025-06-06
- **Contribution**: Official Damiao DM8009 motor datasheet; confirmed ±12.5 rad position range, nominal 20 N·m / peak ~40 N·m torque, 24–48 V operating voltage, and 1 Mbps CAN bus rate. Primary reference for `PMAX`/`VMAX`/`TMAX` decode constants.
- **Applied in**: `hardware/damiao.py`, `docs/can_protocol.md`

---

## Hugging Face: OpenArm LeRobot Integration
- **URL**: https://huggingface.co/docs/lerobot/openarm
- **Date added**: 2025-06-06
- **Contribution**: Documented `OpenArmFollower`/`OpenArmFollowerConfig`, `get_observation()` returning `joint_N.pos/vel/torque` in degrees and Nm, default MIT gains per joint, and the `lerobot-record` / `lerobot-calibrate` CLI. Primary reference for the LeRobot export format and the canonical zero-position workflow.
- **Applied in**: `recording/lerobot_export.py`, `recording/schema.py`, `hardware/damiao.py`

---

## LeRobot Docs: OpenArm (Mintlify mirror)
- **URL**: https://mintlify.wiki/huggingface/lerobot/robots/openarm
- **Date added**: 2025-06-06
- **Contribution**: Supplementary mirror of the LeRobot OpenArm integration docs; confirmed the bimanual CAN bus layout (`can0` right leader, `can1` left leader, `can2`/`can3` followers) and the `lerobot-record --fps=30 --num-episodes=N` invocation.
- **Applied in**: `recording/lerobot_export.py`, `Makefile`

---

## python-can Documentation
- **URL**: https://python-can.readthedocs.io
- **Date added**: 2025-06-06
- **Contribution**: Primary reference for `can.Bus`, `can.Notifier`, `can.AsyncBufferedReader`, CAN-FD message construction (`is_fd=True, bitrate_switch=True`), virtual CAN (`vcan`) setup, and `SO_TIMESTAMPNS` hardware timestamps via `msg.timestamp`. Informed threading model and mock CAN design.
- **Applied in**: `hardware/can_reader.py`, `hardware/mock_can.py`

---

## ZED Multi-Camera Example (Stereolabs)
- **URL**: https://github.com/stereolabs/zed-multi-camera
- **Date added**: 2025-06-06
- **Contribution**: Reference implementation for running multiple ZED cameras concurrently — one `grab()` thread per camera; confirmed `zed.get_timestamp(sl.TIME_REFERENCE.IMAGE).get_nanoseconds()` as the correct nanosecond-precision timestamp API.
- **Applied in**: `cameras/zed_camera.py`, `cameras/sync.py`

---

## ALOHA / ACT: Learning Fine-Grained Bimanual Manipulation (Tony Zhao et al.)
- **URL**: https://github.com/tonyzhaozh/act
- **Date added**: 2025-06-06
- **Contribution**: Canonical prior art for the HDF5 episode schema (`/action`, `/observations/qpos`, `/observations/qvel`, `/observations/images/<cam>`) used in imitation learning datasets. Informed storage format choice and LeRobot export field naming.
- **Applied in**: `recording/episode_writer.py`, `recording/schema.py`, `recording/lerobot_export.py`