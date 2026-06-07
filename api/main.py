"""FastAPI app factory + lifespan context."""
from __future__ import annotations

import logging
import os
import queue
import threading
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import DATA_DIR, latest_joint_state
from api.routes_episodes import router as episodes_router
from api.routes_record import router as record_router
from api.ws import router as ws_router

logger = logging.getLogger(__name__)

MOCK = os.getenv("MOCK", "0") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Start background hardware threads, yield, then tear down."""
    joint_queue: queue.Queue = queue.Queue(maxsize=500)

    if MOCK:
        _start_mock_hardware(joint_queue)
    else:
        _start_real_hardware(joint_queue)

    # Joint state forwarder: drains queue → AtomicRef for WS broadcast
    stop_event = threading.Event()
    fwd_thread = threading.Thread(
        target=_forward_joint_states,
        args=(joint_queue, stop_event),
        daemon=True,
        name="joint-fwd",
    )
    fwd_thread.start()

    yield

    stop_event.set()
    fwd_thread.join(timeout=2.0)
    logger.info("API lifespan shutdown complete")


def _forward_joint_states(
    q: queue.Queue,  # type: ignore[type-arg]
    stop: threading.Event,
) -> None:
    import queue as _queue

    while not stop.is_set():
        try:
            state = q.get(timeout=0.05)
            latest_joint_state.set(state)

            # Also push to active writer if recording
            from api.deps import active_writer
            writer = active_writer.get()
            if writer is not None:
                from cameras.sync import AlignedSample
                import numpy as np
                # In mock mode, create a minimal AlignedSample with empty frames
                sample = AlignedSample(
                    joint_state=state,
                    frames={},
                    timestamps={},
                    worst_sync_ms=0.0,
                )
                try:
                    writer.queue.put_nowait(sample)
                except _queue.Full:
                    pass

        except _queue.Empty:
            continue


def _start_mock_hardware(joint_queue: queue.Queue) -> None:  # type: ignore[type-arg]
    from hardware.mock_can import run as mock_run
    from hardware.can_reader import CANReader
    import can

    bus = can.Bus(interface="socketcan", channel="vcan0")
    reader = CANReader(bus, joint_queue)

    producer_thread = threading.Thread(
        target=mock_run, kwargs={"interface": "vcan0"}, daemon=True, name="mock-can"
    )
    producer_thread.start()
    reader.start()
    logger.info("Mock hardware started")


def _start_real_hardware(joint_queue: queue.Queue) -> None:  # type: ignore[type-arg]
    from hardware.can_reader import CANReader, create_bus

    bus = create_bus(mock=False)
    reader = CANReader(bus, joint_queue)
    reader.start()
    logger.info("Real CAN hardware started on can0")


def create_app() -> FastAPI:
    app = FastAPI(
        title="OpenArm Data Collection API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"] if MOCK else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(episodes_router)
    app.include_router(record_router)
    app.include_router(ws_router)

    return app


app = create_app()
