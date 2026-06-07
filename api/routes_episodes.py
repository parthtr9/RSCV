"""Episode listing and download endpoints."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from api.deps import DATA_DIR, completed_episodes

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/episodes", tags=["episodes"])

CHUNK_SIZE = 1024 * 1024  # 1 MB


@router.get("")
async def list_episodes() -> list[dict[str, object]]:
    return completed_episodes


@router.get("/{episode_id}")
async def get_episode(episode_id: str) -> dict[str, object]:
    ep = _find_episode(episode_id)
    return ep


@router.get("/{episode_id}/download")
async def download_episode(episode_id: str) -> StreamingResponse:
    ep = _find_episode(episode_id)
    path = Path(str(ep["hdf5_path"]))
    if not path.exists():
        raise HTTPException(status_code=404, detail="HDF5 file not found on disk")

    def file_chunks():  # type: ignore[return]
        with open(path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                yield chunk

    filename = f"episode_{episode_id[:8]}.hdf5"
    return StreamingResponse(
        file_chunks(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{episode_id}/export/lerobot")
async def export_lerobot(
    episode_id: str,
    background_tasks: BackgroundTasks,
    task: str = "unknown",
) -> dict[str, str]:
    ep = _find_episode(episode_id)
    job_id = episode_id + "-export"

    background_tasks.add_task(
        _run_export, Path(str(ep["hdf5_path"])), int(str(ep.get("episode_index", 0))), task
    )
    return {"job_id": job_id, "status": "queued"}


def _find_episode(episode_id: str) -> dict[str, object]:
    for ep in completed_episodes:
        if ep.get("episode_id") == episode_id:
            return ep
    raise HTTPException(status_code=404, detail=f"Episode {episode_id!r} not found")


def _run_export(hdf5_path: Path, episode_index: int, task: str) -> None:
    try:
        from recording.lerobot_export import export_episode
        out_dir = DATA_DIR.parent / "lerobot"
        export_episode(hdf5_path, out_dir, episode_index=episode_index, task=task)
    except Exception:
        logger.exception("LeRobot export failed for %s", hdf5_path)
