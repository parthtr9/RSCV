"""FastAPI routes tests using httpx AsyncClient."""
from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from api.main import create_app
from api import deps


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestEpisodesRoutes:
    async def test_list_episodes_empty(self, client: AsyncClient):
        deps.completed_episodes.clear()
        resp = await client.get("/episodes")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_episode_not_found(self, client: AsyncClient):
        resp = await client.get("/episodes/nonexistent-id")
        assert resp.status_code == 404

    async def test_download_not_found(self, client: AsyncClient):
        resp = await client.get("/episodes/bad-id/download")
        assert resp.status_code == 404


class TestRecordRoutes:
    def setup_method(self):
        deps.active_writer.set(None)
        deps.completed_episodes.clear()

    async def test_status_not_recording(self, client: AsyncClient):
        resp = await client.get("/record/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recording"] is False

    async def test_stop_when_not_recording(self, client: AsyncClient):
        resp = await client.post("/record/stop", json={})
        assert resp.status_code == 409

    async def test_start_missing_task(self, client: AsyncClient):
        resp = await client.post("/record/start", json={"fps": 30})
        assert resp.status_code == 422  # validation error

    async def test_start_and_stop(self, client: AsyncClient, tmp_path):
        import api.deps as d
        original_dir = d.DATA_DIR
        d.DATA_DIR = tmp_path / "raw"
        d.DATA_DIR.mkdir(parents=True)

        try:
            resp = await client.post("/record/start", json={"task": "test", "fps": 30})
            assert resp.status_code == 200
            episode_id = resp.json()["episode_id"]
            assert len(episode_id) > 0

            resp2 = await client.get("/record/status")
            assert resp2.json()["recording"] is True

            resp3 = await client.post("/record/stop", json={"is_failure": False})
            assert resp3.status_code == 200
            assert resp3.json()["episode_id"] == episode_id

            resp4 = await client.get("/record/status")
            assert resp4.json()["recording"] is False
        finally:
            d.DATA_DIR = original_dir
            d.active_writer.set(None)

    async def test_double_start_rejected(self, client: AsyncClient, tmp_path):
        import api.deps as d
        d.DATA_DIR = tmp_path / "raw"
        d.DATA_DIR.mkdir(parents=True)

        try:
            await client.post("/record/start", json={"task": "first", "fps": 30})
            resp = await client.post("/record/start", json={"task": "second", "fps": 30})
            assert resp.status_code == 409
        finally:
            writer = d.active_writer.get()
            if writer:
                writer.stop()
            d.active_writer.set(None)
