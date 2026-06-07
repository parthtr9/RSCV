"""
Synthetic CAN-FD frame producer for vcan0.
Emits sinusoidal joint positions so the full pipeline works without hardware.
"""
from __future__ import annotations

import argparse
import logging
import math
import time

import can

from hardware.damiao import (
    JOINT_MAP,
    MOTOR_LIMITS,
    _float_to_uint,
)

logger = logging.getLogger(__name__)

FREQ_HZ = 200  # frames per joint per second
AMPLITUDE_RAD = 1.0  # ± amplitude
FREQ_OFFSETS = [0.0, 0.3, 0.6, 0.9, 1.2, 1.5, 1.8, 2.1]  # phase shifts per joint


def _encode_feedback(
    motor_id: int,
    position: float,
    velocity: float,
    torque: float,
    motor_type: str,
    status: int = 0,
    temp_mos: int = 30,
    temp_rotor: int = 25,
) -> bytes:
    lim = MOTOR_LIMITS[motor_type]
    pos_u  = _float_to_uint(position, -lim.p_max, lim.p_max, 16)
    vel_u  = _float_to_uint(velocity, -lim.v_max, lim.v_max, 12)
    torq_u = _float_to_uint(torque,   -lim.t_max, lim.t_max, 12)

    data = bytearray(8)
    data[0] = ((status & 0x0F) << 4) | (motor_id & 0x0F)
    data[1] = (pos_u >> 8) & 0xFF
    data[2] = pos_u & 0xFF
    data[3] = (vel_u >> 4) & 0xFF
    data[4] = ((vel_u & 0x0F) << 4) | ((torq_u >> 8) & 0x0F)
    data[5] = torq_u & 0xFF
    data[6] = temp_mos & 0xFF
    data[7] = temp_rotor & 0xFF
    return bytes(data)


def run(interface: str = "vcan0") -> None:
    bus = can.Bus(interface="virtual", channel=interface)
    logger.info("MockCAN running on %s at %d Hz", interface, FREQ_HZ)

    period = 1.0 / FREQ_HZ
    t_start = time.monotonic()

    try:
        while True:
            t = time.monotonic() - t_start
            for i, joint in enumerate(JOINT_MAP):
                pos = AMPLITUDE_RAD * math.sin(2 * math.pi * 0.5 * t + FREQ_OFFSETS[i])
                vel = AMPLITUDE_RAD * math.pi * math.cos(2 * math.pi * 0.5 * t + FREQ_OFFSETS[i])
                torque = 0.1 * pos

                payload = _encode_feedback(
                    motor_id=joint.send_id,
                    position=pos,
                    velocity=vel,
                    torque=torque,
                    motor_type=joint.motor_type,
                )
                msg = can.Message(
                    arbitration_id=joint.recv_id,
                    data=payload,
                    is_extended_id=False,
                    is_fd=False,
                )
                try:
                    bus.send(msg)
                except can.CanError as e:
                    logger.warning("send error: %s", e)

            time.sleep(period)
    except KeyboardInterrupt:
        pass
    finally:
        bus.shutdown()
        logger.info("MockCAN stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Synthetic CAN frame producer")
    parser.add_argument("--interface", default="vcan0")
    args = parser.parse_args()
    run(interface=args.interface)
