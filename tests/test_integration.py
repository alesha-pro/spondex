"""Integration tests: full RPC lifecycle with mock engine/scheduler/db."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from spondex.server.rpc import DaemonState, create_rpc_app


def _make_full_state() -> DaemonState:
    """Create a DaemonState with mock engine, scheduler, and db."""
    state = DaemonState()

    # Mock engine
    engine = MagicMock()
    engine.get_status.return_value = {"state": "idle", "last_stats": None}
    state.engine = engine

    # Mock scheduler
    sched = MagicMock()
    sched.get_status.return_value = {
        "mode": "incremental",
        "interval_minutes": 30,
        "paused": False,
        "last_sync": None,
        "next_sync": None,
    }
    sched.trigger_now = MagicMock()
    sched.pause = MagicMock()
    sched.resume = MagicMock()
    state.scheduler = sched

    # Mock db
    db = AsyncMock()
    db.count_track_mappings = AsyncMock(return_value=42)
    db.count_unmatched = AsyncMock(return_value=5)
    db.count_sync_runs = AsyncMock(return_value=3)
    state.db = db

    return state


# ---------------------------------------------------------------------------
# Full lifecycle: status → sync_now → pause → resume → shutdown
# ---------------------------------------------------------------------------


def test_full_rpc_lifecycle():
    """Walk through the full daemon lifecycle via RPC."""
    state = _make_full_state()
    app = create_rpc_app(state)
    client = TestClient(app)

    # 1. Status — should report idle with counts
    resp = client.post("/rpc", json={"cmd": "status"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["sync"]["state"] == "idle"
    assert body["data"]["counts"]["track_mappings"] == 42
    assert body["data"]["counts"]["unmatched"] == 5
    assert body["data"]["counts"]["sync_runs"] == 3

    # 2. Sync now
    resp = client.post("/rpc", json={"cmd": "sync_now", "params": {"mode": "full"}})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    state.scheduler.trigger_now.assert_called_once_with(mode="full")

    # 3. Pause
    resp = client.post("/rpc", json={"cmd": "pause"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    state.scheduler.pause.assert_called_once()

    # 4. Resume
    resp = client.post("/rpc", json={"cmd": "resume"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    state.scheduler.resume.assert_called_once()

    # 5. Shutdown
    assert not state.shutdown_event.is_set()
    resp = client.post("/rpc", json={"cmd": "shutdown"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert state.shutdown_event.is_set()


# ---------------------------------------------------------------------------
# Status includes counts from DB
# ---------------------------------------------------------------------------


def test_status_includes_db_counts():
    """Status response includes track_mappings, unmatched, sync_runs counts."""
    state = _make_full_state()
    app = create_rpc_app(state)
    client = TestClient(app)

    resp = client.post("/rpc", json={"cmd": "status"})
    data = resp.json()["data"]

    assert "counts" in data
    assert data["counts"]["track_mappings"] == 42
    assert data["counts"]["unmatched"] == 5
    assert data["counts"]["sync_runs"] == 3


# ---------------------------------------------------------------------------
# Status without DB (no counts section)
# ---------------------------------------------------------------------------


def test_status_without_db():
    """Status response works without a DB attached."""
    state = DaemonState()
    app = create_rpc_app(state)
    client = TestClient(app)

    resp = client.post("/rpc", json={"cmd": "status"})
    data = resp.json()["data"]
    assert "counts" not in data
