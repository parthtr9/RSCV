"""Recording control endpoints."""
from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.deps import DATA_DIR, active_writer, completed_episodes
from recording.episode_writer import EpisodeWriter
from recording.schema import DEFAULT_FPS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/record", tags=["record"])


class StartRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=256)
    fps: int = Field(DEFAULT_FPS, ge=1, le=120)


class StartResponse(BaseModel):
    episode_id: str


class StopRequest(BaseModel):
    is_failure: bool = False


class StopResponse(BaseModel):
    episode_id: str
    frames: int
    duration_s: float


class StatusResponse(BaseModel):
    recording: bool
    episode_id: str | None = None
    frames_so_far: int = 0
    elapsed_s: float = 0.0


_record_start_time: float | None = None


@router.post("/start", response_model=StartResponse)
async def start_recording(req: StartRequest) -> StartResponse:
    global _record_start_time

    if active_writer.get() is not None:
        raise HTTPException(status_code=409, detail="Already recording")

    writer = EpisodeWriter(
        output_dir=DATA_DIR,
        task=req.task,
        fps=req.fps,
    )
    writer.start()
    active_writer.set(writer)
    _record_start_time = time.monotonic()

    logger.info("Recording started: episode_id=%s task=%r", writer.episode_id, req.task)
    return StartResponse(episode_id=writer.episode_id)


@router.post("/stop", response_model=StopResponse)
async def stop_recording(req: StopRequest) -> StopResponse:
    global _record_start_time

    writer = active_writer.get()
    if writer is None:
        raise HTTPException(status_code=409, detail="Not recording")

    active_writer.set(None)
    elapsed = time.monotonic() - (_record_start_time or time.monotonic())
    path, n_frames = writer.stop(is_failure=req.is_failure)
    _record_start_time = None

    completed_episodes.append(
        {
            "episode_id":    writer.episode_id,
            "task":          writer.queue.maxsize,  # placeholder
            "fps":           writer._fps,
            "frames":        n_frames,
            "duration_s":    round(elapsed, 2),
            "hdf5_path":     str(path),
            "is_failure":    req.is_failure,
            "episode_index": len(completed_episodes),
        }
    )

    logger.info("Recording stopped: %d frames in %.1f s", n_frames, elapsed)
    return StopResponse(
        episode_id=writer.episode_id,
        frames=n_frames,
        duration_s=round(elapsed, 2),
    )


@router.get("/status", response_model=StatusResponse)
async def recording_status() -> StatusResponse:
    writer = active_writer.get()
    if writer is None:
        return StatusResponse(recording=False)

    elapsed = time.monotonic() - (_record_start_time or time.monotonic())
    frames_so_far = writer._n_frames

    return StatusResponse(
        recording=True,
        episode_id=writer.episode_id,
        frames_so_far=frames_so_far,
        elapsed_s=round(elapsed, 2),
    )
