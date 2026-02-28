"""Tests for spondex.cli module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from spondex.cli import app


runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper fixture: patch get_base_dir in the cli module as well
# ---------------------------------------------------------------------------


@pytest.fixture()
def cli_base_dir(base_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Extend the shared ``base_dir`` fixture to also patch the reference
    that ``spondex.cli`` holds after its ``from spondex.config import get_base_dir``
    import.
    """
    monkeypatch.setattr("spondex.cli.get_base_dir", lambda: base_dir)
    return base_dir


# ---------------------------------------------------------------------------
# 1. --help
# ---------------------------------------------------------------------------


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "spondex" in result.output.lower()


# ---------------------------------------------------------------------------
# 2. status when daemon not running
# ---------------------------------------------------------------------------


def test_status_daemon_not_running(cli_base_dir: Path):
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "not running" in result.output.lower() or "daemon" in result.output.lower()


# ---------------------------------------------------------------------------
# 3. stop when daemon not running
# ---------------------------------------------------------------------------


def test_stop_daemon_not_running(cli_base_dir: Path):
    with patch("spondex.cli.Daemon" if False else "spondex.daemon.Daemon") as _:
        pass

    # The stop command first checks for the socket, then falls back to Daemon.
    # With no socket and Daemon.is_running returning False, it should say
    # "not running".
    with patch("spondex.daemon.Daemon.is_running", return_value=False):
        result = runner.invoke(app, ["stop"])

    assert result.exit_code == 0
    assert "not running" in result.output.lower()


# ---------------------------------------------------------------------------
# 4. logs when no log file exists
# ---------------------------------------------------------------------------


def test_logs_no_log_file(cli_base_dir: Path):
    # Make sure the log file does NOT exist.
    log_file = cli_base_dir / "logs" / "daemon.log"
    assert not log_file.exists()

    result = runner.invoke(app, ["logs"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower() or "log file" in result.output.lower()


# ---------------------------------------------------------------------------
# 5. logs with a log file present
# ---------------------------------------------------------------------------


def test_logs_with_log_file(cli_base_dir: Path):
    log_dir = cli_base_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "daemon.log"
    log_file.write_text("2026-01-01 INFO  Daemon started successfully\n")

    result = runner.invoke(app, ["logs"])
    assert result.exit_code == 0
    assert "Daemon started successfully" in result.output


# ---------------------------------------------------------------------------
# 6. start when daemon is already running
# ---------------------------------------------------------------------------


def test_start_already_running(cli_base_dir: Path):
    with (
        patch("spondex.daemon.Daemon.is_running", return_value=True),
        patch("spondex.daemon.Daemon.get_pid", return_value=12345),
    ):
        result = runner.invoke(app, ["start"])

    assert result.exit_code == 0
    assert "already running" in result.output.lower()
    assert "12345" in result.output
