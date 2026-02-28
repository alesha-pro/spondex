"""Tests for the RPC server module."""

from __future__ import annotations

from fastapi.testclient import TestClient

from spondex.server.rpc import DaemonState, create_rpc_app


def _make_client() -> tuple[TestClient, DaemonState]:
    """Create a fresh DaemonState + TestClient pair."""
    state = DaemonState()
    app = create_rpc_app(state)
    return TestClient(app), state


# ---------------------------------------------------------------------------
# RPC endpoint tests
# ---------------------------------------------------------------------------


def test_ping() -> None:
    client, _state = _make_client()
    resp = client.post("/rpc", json={"cmd": "ping"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True


def test_status() -> None:
    client, _state = _make_client()
    resp = client.post("/rpc", json={"cmd": "status"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "state" in body["data"]
    assert "uptime_seconds" in body["data"]
    assert "started_at" in body["data"]


def test_health_rpc() -> None:
    client, _state = _make_client()
    resp = client.post("/rpc", json={"cmd": "health"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "uptime_seconds" in body["data"]


def test_health_get_endpoint() -> None:
    client, _state = _make_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "uptime_seconds" in body["data"]


def test_shutdown() -> None:
    client, state = _make_client()
    resp = client.post("/rpc", json={"cmd": "shutdown"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "message" in body["data"]
    assert state.shutdown_event.is_set()


def test_unknown_command() -> None:
    client, _state = _make_client()
    resp = client.post("/rpc", json={"cmd": "foobar"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] is not None
    assert "unknown" in body["error"].lower()


# ---------------------------------------------------------------------------
# DaemonState unit tests
# ---------------------------------------------------------------------------


def test_daemon_state_get_status() -> None:
    state = DaemonState()
    status = state.get_status()
    assert "state" in status
    assert "uptime_seconds" in status
    assert "started_at" in status
    assert isinstance(status["uptime_seconds"], float)


def test_daemon_state_request_shutdown() -> None:
    state = DaemonState()
    assert not state.shutdown_event.is_set()
    state.request_shutdown()
    assert state.shutdown_event.is_set()
