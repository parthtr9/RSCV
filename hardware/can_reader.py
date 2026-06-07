"""python-can FD bus wrapper with asyncio-safe buffered listener."""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from collections.abc import Callable

import can
import numpy as np

from hardware.damiao import (
    JOINT_MAP,
    RECV_ID_MAP,
    JointState,
    MotorFeedback,
    NUM_JOINTS,
    decode_feedback,
)

logger = logging.getLogger(__name__)


def create_bus(mock: bool = False, channel: str = "can0") -> can.BusABC:
    if mock:
        return can.Bus(interface="virtual", channel="vcan0")
    return can.Bus(interface="socketcan", channel=channel, fd=True)


class CANReader:
    """
    Listens on CAN bus via python-can Notifier.
    Assembles per-tick JointState from individual motor feedback frames.
    Pushes assembled states into joint_queue for downstream consumers.
    """

    def __init__(
        self,
        bus: can.BusABC,
        joint_queue: "queue.Queue[JointState]",
        queue_maxsize: int = 500,
    ) -> None:
        self._bus = bus
        self._queue = joint_queue
        self._partial: dict[int, MotorFeedback] = {}  # recv_id → latest feedback
        self._lock = threading.Lock()
        self._notifier: can.Notifier | None = None
        self._running = False

    def start(self) -> None:
        self._running = True
        self._notifier = can.Notifier(self._bus, [self._on_message])
        logger.info("CANReader started")
        self._try_set_realtime()

    def stop(self) -> None:
        self._running = False
        if self._notifier:
            self._notifier.stop()
        logger.info("CANReader stopped")

    def _on_message(self, msg: can.Message) -> None:
        if not self._running:
            return
        recv_id = msg.arbitration_id
        if recv_id not in RECV_ID_MAP:
            return

        try:
            fb = decode_feedback(bytes(msg.data), recv_id)
        except ValueError:
            logger.debug("Bad frame arb_id=0x%02X len=%d", recv_id, len(msg.data))
            return

        joint_idx = list(RECV_ID_MAP.keys()).index(recv_id)
        with self._lock:
            self._partial[recv_id] = fb
            if len(self._partial) == NUM_JOINTS:
                state = self._assemble(msg.timestamp or time.monotonic())
                self._partial.clear()
                try:
                    self._queue.put_nowait(state)
                except queue.Full:
                    logger.warning("joint_queue full, dropping frame")

    def _assemble(self, timestamp: float) -> JointState:
        state = JointState.zeros(timestamp)
        for idx, joint in enumerate(JOINT_MAP):
            fb = self._partial.get(joint.recv_id)
            if fb is not None:
                state.qpos[idx]   = fb.position
                state.qvel[idx]   = fb.velocity
                state.torque[idx] = fb.torque
                state.status[idx] = fb.status
        return state

    @staticmethod
    def _try_set_realtime() -> None:
        try:
            import ctypes
            SCHED_FIFO = 1
            param = ctypes.c_int(10)
            ctypes.cdll.LoadLibrary("libc.so.6").sched_setscheduler(
                0, SCHED_FIFO, ctypes.byref(param)
            )
            logger.info("CAN listener running SCHED_FIFO priority 10")
        except Exception:
            logger.debug("Could not set SCHED_FIFO (needs CAP_SYS_NICE)")
