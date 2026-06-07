"""Damiao CAN-FD motor encode/decode and joint map."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np


# ── Motor constant limits (from dm_motor_constants.hpp) ──────────────────────
# Position range is ±12.5 rad for all Damiao motors.
# Velocity and torque limits vary by model — values below from datasheet.
@dataclass(frozen=True)
class MotorLimits:
    p_max: float   # rad
    v_max: float   # rad/s
    t_max: float   # Nm


MOTOR_LIMITS: dict[str, MotorLimits] = {
    "DM8009":   MotorLimits(p_max=12.5, v_max=45.0,  t_max=54.0),
    "DM8009P":  MotorLimits(p_max=12.5, v_max=45.0,  t_max=54.0),
    "DM4340":   MotorLimits(p_max=12.5, v_max=50.0,  t_max=28.0),
    "DM4340P":  MotorLimits(p_max=12.5, v_max=50.0,  t_max=28.0),
    "DM4310":   MotorLimits(p_max=12.5, v_max=30.0,  t_max=10.0),
}


# ── Joint map (ground truth — never hardcode elsewhere) ──────────────────────
class JointEntry(NamedTuple):
    name: str
    motor_type: str
    send_id: int
    recv_id: int


JOINT_MAP: tuple[JointEntry, ...] = (
    JointEntry("joint_1", "DM8009P", 0x01, 0x11),
    JointEntry("joint_2", "DM8009P", 0x02, 0x12),
    JointEntry("joint_3", "DM4340",  0x03, 0x13),
    JointEntry("joint_4", "DM4340P", 0x04, 0x14),
    JointEntry("joint_5", "DM4310",  0x05, 0x15),
    JointEntry("joint_6", "DM4310",  0x06, 0x16),
    JointEntry("joint_7", "DM4310",  0x07, 0x17),
    JointEntry("gripper", "DM4310",  0x08, 0x18),
)

# recv_id → joint entry for fast lookup
RECV_ID_MAP: dict[int, JointEntry] = {j.recv_id: j for j in JOINT_MAP}
SEND_ID_MAP: dict[int, JointEntry] = {j.send_id: j for j in JOINT_MAP}

NUM_JOINTS = len(JOINT_MAP)


# ── System command payloads ───────────────────────────────────────────────────
CMD_ENABLE    = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFC])
CMD_DISABLE   = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFD])
CMD_SET_ZERO  = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFE])
CMD_CLR_ERROR = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFB])


# ── Decode helpers ────────────────────────────────────────────────────────────
def _uint_to_float(u: int, x_min: float, x_max: float, n_bits: int) -> float:
    """Linear mapping from unsigned int → physical value."""
    return x_min + (u / ((1 << n_bits) - 1)) * (x_max - x_min)


def _float_to_uint(x: float, x_min: float, x_max: float, n_bits: int) -> int:
    """Linear mapping from physical value → unsigned int (clamped)."""
    x = max(x_min, min(x_max, x))
    return round((x - x_min) / (x_max - x_min) * ((1 << n_bits) - 1))


@dataclass
class MotorFeedback:
    motor_id: int
    status: int
    position: float   # rad
    velocity: float   # rad/s
    torque: float     # Nm
    temp_mos: float   # °C
    temp_rotor: float # °C


def decode_feedback(data: bytes, recv_id: int) -> MotorFeedback:
    """Decode 8-byte Damiao feedback frame."""
    if len(data) != 8:
        raise ValueError(f"Expected 8 bytes, got {len(data)}")

    joint = RECV_ID_MAP.get(recv_id)
    if joint is None:
        raise ValueError(f"Unknown recv_id 0x{recv_id:02X}")

    limits = MOTOR_LIMITS[joint.motor_type]

    motor_id = data[0] & 0x0F
    status   = (data[0] >> 4) & 0x0F

    pos_u  = (data[1] << 8) | data[2]
    vel_u  = (data[3] << 4) | (data[4] >> 4)
    torq_u = ((data[4] & 0x0F) << 8) | data[5]

    position = _uint_to_float(pos_u,  -limits.p_max, limits.p_max, 16)
    velocity = _uint_to_float(vel_u,  -limits.v_max, limits.v_max, 12)
    torque   = _uint_to_float(torq_u, -limits.t_max, limits.t_max, 12)

    temp_mos   = float(data[6])
    temp_rotor = float(data[7])

    return MotorFeedback(
        motor_id=motor_id,
        status=status,
        position=position,
        velocity=velocity,
        torque=torque,
        temp_mos=temp_mos,
        temp_rotor=temp_rotor,
    )


def encode_mit_command(
    send_id: int,
    position: float,
    velocity: float,
    kp: float,
    kd: float,
    torque_ff: float,
) -> bytes:
    """Encode MIT-mode position/velocity command frame (8 bytes)."""
    joint = SEND_ID_MAP.get(send_id)
    if joint is None:
        raise ValueError(f"Unknown send_id 0x{send_id:02X}")

    limits = MOTOR_LIMITS[joint.motor_type]

    pos_u  = _float_to_uint(position,   -limits.p_max, limits.p_max, 16)
    vel_u  = _float_to_uint(velocity,   -limits.v_max, limits.v_max, 12)
    torq_u = _float_to_uint(torque_ff,  -limits.t_max, limits.t_max, 12)
    kp_u   = _float_to_uint(kp,   0.0, 500.0, 12)
    kd_u   = _float_to_uint(kd,   0.0,   5.0, 12)

    data = bytearray(8)
    data[0] = (pos_u >> 8) & 0xFF
    data[1] = pos_u & 0xFF
    data[2] = vel_u >> 4
    data[3] = ((vel_u & 0x0F) << 4) | (kp_u >> 8)
    data[4] = kp_u & 0xFF
    data[5] = kd_u >> 4
    data[6] = ((kd_u & 0x0F) << 4) | (torq_u >> 8)
    data[7] = torq_u & 0xFF

    return bytes(data)


@dataclass
class JointState:
    """Decoded state for all joints at a single timestamp."""
    timestamp: float              # time.monotonic()
    qpos:   np.ndarray            # (8,) float32 rad
    qvel:   np.ndarray            # (8,) float32 rad/s
    torque: np.ndarray            # (8,) float32 Nm
    status: list[int]             # per-joint status nibble

    @classmethod
    def zeros(cls, timestamp: float = 0.0) -> "JointState":
        return cls(
            timestamp=timestamp,
            qpos=np.zeros(NUM_JOINTS, dtype=np.float32),
            qvel=np.zeros(NUM_JOINTS, dtype=np.float32),
            torque=np.zeros(NUM_JOINTS, dtype=np.float32),
            status=[0] * NUM_JOINTS,
        )
