"""Round-trip encode/decode tests for Damiao CAN frame protocol."""
from __future__ import annotations

import math

import numpy as np
import pytest

from hardware.damiao import (
    JOINT_MAP,
    MOTOR_LIMITS,
    JointState,
    NUM_JOINTS,
    _float_to_uint,
    _uint_to_float,
    decode_feedback,
    encode_mit_command,
)


class TestLinearMapping:
    def test_uint_to_float_min(self):
        assert _uint_to_float(0, -12.5, 12.5, 16) == pytest.approx(-12.5)

    def test_uint_to_float_max(self):
        assert _uint_to_float(0xFFFF, -12.5, 12.5, 16) == pytest.approx(12.5, rel=1e-4)

    def test_uint_to_float_mid(self):
        v = _uint_to_float(0x7FFF, -12.5, 12.5, 16)
        assert abs(v) < 0.1  # near zero

    def test_float_to_uint_roundtrip(self):
        for x in [-12.0, -5.0, 0.0, 5.0, 12.0]:
            u = _float_to_uint(x, -12.5, 12.5, 16)
            back = _uint_to_float(u, -12.5, 12.5, 16)
            assert abs(back - x) < 0.01, f"roundtrip failed for {x}"

    def test_float_to_uint_clamp_low(self):
        u = _float_to_uint(-999.0, -12.5, 12.5, 16)
        assert u == 0

    def test_float_to_uint_clamp_high(self):
        u = _float_to_uint(999.0, -12.5, 12.5, 16)
        assert u == 0xFFFF


class TestDecodeFeedback:
    def _make_frame(
        self,
        motor_id: int,
        position: float,
        velocity: float,
        torque: float,
        motor_type: str,
        status: int = 0,
        temp_mos: int = 30,
        temp_rotor: int = 25,
    ) -> bytes:
        from hardware.mock_can import _encode_feedback
        return _encode_feedback(
            motor_id, position, velocity, torque, motor_type,
            status, temp_mos, temp_rotor
        )

    def test_decode_joint1_zero_position(self):
        frame = self._make_frame(
            motor_id=0x01, position=0.0, velocity=0.0, torque=0.0,
            motor_type="DM8009P",
        )
        fb = decode_feedback(frame, recv_id=0x11)
        assert abs(fb.position) < 0.05
        assert abs(fb.velocity) < 0.1
        assert fb.temp_mos == 30
        assert fb.temp_rotor == 25

    def test_decode_joint1_positive_position(self):
        target = 3.14
        frame = self._make_frame(
            motor_id=0x01, position=target, velocity=1.0, torque=2.0,
            motor_type="DM8009P",
        )
        fb = decode_feedback(frame, recv_id=0x11)
        assert abs(fb.position - target) < 0.02

    def test_decode_all_joints(self):
        for joint in JOINT_MAP:
            frame = self._make_frame(
                motor_id=joint.send_id, position=1.0, velocity=0.5, torque=0.1,
                motor_type=joint.motor_type,
            )
            fb = decode_feedback(frame, recv_id=joint.recv_id)
            assert abs(fb.position - 1.0) < 0.05

    def test_decode_bad_length(self):
        with pytest.raises(ValueError, match="Expected 8 bytes"):
            decode_feedback(b"\x00" * 7, recv_id=0x11)

    def test_decode_unknown_recv_id(self):
        with pytest.raises(ValueError, match="Unknown recv_id"):
            decode_feedback(b"\x00" * 8, recv_id=0xFF)

    def test_decode_gripper(self):
        frame = self._make_frame(
            motor_id=0x08, position=-1.0, velocity=0.0, torque=0.0,
            motor_type="DM4310",
        )
        fb = decode_feedback(frame, recv_id=0x18)
        assert abs(fb.position - (-1.0)) < 0.05


class TestJointMap:
    def test_recv_id_is_send_id_plus_0x10(self):
        for j in JOINT_MAP:
            assert j.recv_id == j.send_id + 0x10

    def test_num_joints(self):
        assert NUM_JOINTS == 8

    def test_all_motor_types_in_limits(self):
        for j in JOINT_MAP:
            assert j.motor_type in MOTOR_LIMITS

    def test_joint_state_zeros(self):
        state = JointState.zeros()
        assert state.qpos.shape == (NUM_JOINTS,)
        assert np.all(state.qpos == 0.0)
