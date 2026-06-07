"""Shared FastAPI dependencies — recorder singleton and joint state bus."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

from hardware.damiao import JointState

if TYPE_CHECKING:
    from recording.episode_writer import EpisodeWriter


class AtomicRef[T]:
    """Thread-safe single-value reference."""

    def __init__(self, initial: T) -> None:
        self._value = initial
        self._lock = threading.Lock()

    def get(self) -> T:
        with self._lock:
            return self._value

    def set(self, value: T) -> None:
        with self._lock:
            self._value = value


# ── Singletons (populated during lifespan) ───────────────────────────────────
latest_joint_state: AtomicRef[JointState | None] = AtomicRef(None)

# Active episode writer — None when not recording
active_writer: AtomicRef["EpisodeWriter | None"] = AtomicRef(None)

# Completed episodes metadata (in-memory for now; persist to DB for production)
completed_episodes: list[dict[str, object]] = []

DATA_DIR = Path("data/raw")
DATA_DIR.mkdir(parents=True, exist_ok=True)
