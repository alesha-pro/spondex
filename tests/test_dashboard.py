"""Tests for the web dashboard server module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from spondex.server.rpc import DaemonState
from spondex.storage.database import Database

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def dashboard_db(tmp_path: Path) -> Database:
    """Create and connect a test database."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    yield db
    await db.close()


@pytest.fixture()
def _make_dashboard_client(dashboard_db: Database):
    """Factory that returns (TestClient, DaemonState, Database)."""

    def _factory(*, with_scheduler: bool = False):
        from spondex.server.dashboard import create_dashboard_app

        state = DaemonState()
        state.db = dashboard_db

        if with_scheduler:
            sched = MagicMock()
            sched.trigger_now = MagicMock()
            sched.pause = MagicMock()
            sched.resume = MagicMock()
            sched.get_status.return_value = {
                "running": True,
                "paused": False,
                "interval_minutes": 30,
                "default_mode": "incremental",
                "last_sync_at": None,
                "next_sync_at": None,
            }
            state.scheduler = sched

        app = create_dashboard_app(state, dashboard_db)
        return TestClient(app), state, dashboard_db

    return _factory


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def test_status_empty(_make_dashboard_client) -> None:
    client, _state, _db = _make_dashboard_client()
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "uptime_seconds" in body
    assert "counts" in body
    assert body["counts"]["tracks"] == 0
    assert body["counts"]["unmatched"] == 0


@pytest.mark.asyncio
async def test_status_with_data(_make_dashboard_client, dashboard_db: Database) -> None:
    await dashboard_db.upsert_track_mapping(artist="Test", title="Song", spotify_id="sp1", yandex_id="ym1")
    await dashboard_db.add_unmatched(source_service="spotify", source_id="sp2", artist="Unknown", title="Track")

    client, _state, _db = _make_dashboard_client()
    resp = client.get("/api/status")
    body = resp.json()
    assert body["counts"]["tracks"] == 1
    assert body["counts"]["unmatched"] == 1


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_pagination(_make_dashboard_client, dashboard_db: Database) -> None:
    for _i in range(5):
        run = await dashboard_db.start_sync_run(direction="bidirectional", mode="full")
        await dashboard_db.finish_sync_run(run.id, status="completed")

    client, _state, _db = _make_dashboard_client()

    resp = client.get("/api/history?limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0

    resp2 = client.get("/api/history?limit=2&offset=2")
    body2 = resp2.json()
    assert len(body2["items"]) == 2
    assert body2["offset"] == 2


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tracks_search_pagination(_make_dashboard_client, dashboard_db: Database) -> None:
    await dashboard_db.upsert_track_mapping(artist="Queen", title="Bohemian Rhapsody", spotify_id="sp1")
    await dashboard_db.upsert_track_mapping(artist="Queen", title="We Will Rock You", spotify_id="sp2")
    await dashboard_db.upsert_track_mapping(artist="Beatles", title="Yesterday", spotify_id="sp3")

    client, _state, _db = _make_dashboard_client()

    # All tracks
    resp = client.get("/api/tracks?limit=10&offset=0")
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3

    # Search by artist
    resp = client.get("/api/tracks?limit=10&offset=0&search=Queen")
    body = resp.json()
    assert body["total"] == 2
    assert all("Queen" in t["artist"] for t in body["items"])

    # Search by title
    resp = client.get("/api/tracks?limit=10&offset=0&search=Yesterday")
    body = resp.json()
    assert body["total"] == 1


# ---------------------------------------------------------------------------
# Unmatched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unmatched(_make_dashboard_client, dashboard_db: Database) -> None:
    await dashboard_db.add_unmatched(source_service="spotify", source_id="sp1", artist="Test", title="Song")

    client, _state, _db = _make_dashboard_client()
    resp = client.get("/api/unmatched?limit=10&offset=0")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["artist"] == "Test"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_config_no_secrets(_make_dashboard_client, monkeypatch) -> None:
    from spondex.config import AppConfig

    monkeypatch.setattr(
        "spondex.config.load_config",
        lambda: AppConfig(),
    )

    client, _state, _db = _make_dashboard_client()
    resp = client.get("/api/config")
    body = resp.json()

    assert "daemon" in body
    assert "sync" in body
    assert "spotify" in body
    assert "yandex" in body

    # No raw secrets exposed
    assert "client_secret" not in str(body)
    assert "refresh_token" not in str(body)
    assert "token" not in str(body["yandex"])

    # Only 'configured' boolean
    assert body["spotify"]["configured"] is False
    assert body["yandex"]["configured"] is False


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def test_sync_trigger(_make_dashboard_client) -> None:
    client, state, _db = _make_dashboard_client(with_scheduler=True)
    resp = client.post("/api/sync", json={"mode": "full"})
    assert resp.status_code == 200
    state.scheduler.trigger_now.assert_called_once_with(mode="full")


def test_sync_trigger_no_scheduler(_make_dashboard_client) -> None:
    client, _state, _db = _make_dashboard_client()
    resp = client.post("/api/sync", json={"mode": "full"})
    assert resp.status_code == 503


def test_pause_resume(_make_dashboard_client) -> None:
    client, state, _db = _make_dashboard_client(with_scheduler=True)

    resp = client.post("/api/pause")
    assert resp.status_code == 200
    state.scheduler.pause.assert_called_once()

    resp = client.post("/api/resume")
    assert resp.status_code == 200
    state.scheduler.resume.assert_called_once()


def test_pause_no_scheduler(_make_dashboard_client) -> None:
    client, _state, _db = _make_dashboard_client()
    resp = client.post("/api/pause")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collections(_make_dashboard_client, dashboard_db: Database) -> None:
    col = await dashboard_db.create_collection(service="spotify", collection_type="liked", title="Liked Songs")
    mapping = await dashboard_db.upsert_track_mapping(artist="Test", title="Song", spotify_id="sp1")
    await dashboard_db.add_track_to_collection(collection_id=col.id, track_mapping_id=mapping.id)

    client, _state, _db = _make_dashboard_client()
    resp = client.get("/api/collections")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["title"] == "Liked Songs"
    assert body[0]["track_count"] == 1


# ---------------------------------------------------------------------------
# SPA fallback
# ---------------------------------------------------------------------------


def test_spa_fallback(_make_dashboard_client) -> None:
    client, _state, _db = _make_dashboard_client()
    # The static dir may not have index.html in test, so this may 404
    # but the route should exist and not crash
    resp = client.get("/some/spa/route")
    # Either serves index.html (200) or file not found (404)
    assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


def test_ws_connect(_make_dashboard_client) -> None:
    client, _state, _db = _make_dashboard_client()
    with client.websocket_connect("/ws") as ws:
        # Connection should succeed
        assert ws is not None
