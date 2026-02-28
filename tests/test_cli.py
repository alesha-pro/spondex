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
    # Create config so wizard is not triggered.
    (cli_base_dir / "config.toml").write_text("[daemon]\nlog_level = \"info\"\n")

    with (
        patch("spondex.daemon.Daemon.is_running", return_value=True),
        patch("spondex.daemon.Daemon.get_pid", return_value=12345),
    ):
        result = runner.invoke(app, ["start"])

    assert result.exit_code == 0
    assert "already running" in result.output.lower()
    assert "12345" in result.output


# ---------------------------------------------------------------------------
# 7. start triggers wizard when no config
# ---------------------------------------------------------------------------


def test_start_runs_wizard_when_no_config(cli_base_dir: Path):
    """start command runs wizard when config.toml is absent."""
    from spondex.config import AppConfig

    assert not (cli_base_dir / "config.toml").exists()

    with (
        patch("spondex.wizard.run_wizard", return_value=AppConfig()) as mock_wizard,
        patch("spondex.daemon.Daemon.is_running", return_value=True),
        patch("spondex.daemon.Daemon.get_pid", return_value=99),
    ):
        result = runner.invoke(app, ["start"])

    mock_wizard.assert_called_once()
    assert (cli_base_dir / "config.toml").exists()
    assert result.exit_code == 0


def test_start_skips_wizard_when_config_exists(cli_base_dir: Path):
    """start command skips wizard when config.toml is present."""
    (cli_base_dir / "config.toml").write_text("[daemon]\nlog_level = \"info\"\n")

    with (
        patch("spondex.wizard.run_wizard") as mock_wizard,
        patch("spondex.daemon.Daemon.is_running", return_value=True),
        patch("spondex.daemon.Daemon.get_pid", return_value=42),
    ):
        result = runner.invoke(app, ["start"])

    mock_wizard.assert_not_called()
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 8. config command
# ---------------------------------------------------------------------------


def test_config_shows_sections(cli_base_dir: Path):
    """config command displays all sections with masked secrets."""
    from pydantic import SecretStr

    from spondex.config import AppConfig, SpotifyConfig, YandexConfig, save_config

    save_config(
        AppConfig(
            spotify=SpotifyConfig(
                client_id="test-id",
                client_secret=SecretStr("secret"),
                refresh_token=SecretStr("token"),
            ),
            yandex=YandexConfig(token=SecretStr("ym-tok")),
        )
    )

    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "test-id" in result.output
    assert "***" in result.output
    # Secrets must NOT appear in output
    assert "secret" not in result.output.lower().replace("client_secret", "")
    assert "ym-tok" not in result.output


def test_config_empty_secrets_show_not_set(cli_base_dir: Path):
    """config command shows '(not set)' for empty secrets."""
    from spondex.config import AppConfig, save_config

    save_config(AppConfig())

    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "not set" in result.output


# ---------------------------------------------------------------------------
# 9. db command
# ---------------------------------------------------------------------------


def test_db_no_database(cli_base_dir: Path):
    """db command reports missing database."""
    result = runner.invoke(app, ["db", "status"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_db_empty_database(cli_base_dir: Path):
    """db command shows table stats for an empty database."""
    import sqlite3

    db_path = cli_base_dir / "spondex.db"
    conn = sqlite3.connect(db_path)
    # Create tables using the same schema
    from spondex.storage.database import _SCHEMA

    conn.executescript(_SCHEMA)
    conn.close()

    result = runner.invoke(app, ["db", "status"])
    assert result.exit_code == 0
    assert "track_mapping" in result.output
    assert "collection" in result.output
    assert "sync_runs" in result.output


def test_db_with_data(cli_base_dir: Path):
    """db command shows counts and last sync info."""
    import json
    import sqlite3

    db_path = cli_base_dir / "spondex.db"
    conn = sqlite3.connect(db_path)
    from spondex.storage.database import _SCHEMA

    conn.executescript(_SCHEMA)

    # Insert some data
    conn.execute(
        "INSERT INTO track_mapping (spotify_id, artist, title) VALUES ('sp1', 'Artist', 'Song')"
    )
    conn.execute(
        "INSERT INTO sync_runs (started_at, finished_at, direction, mode, status, stats_json) "
        "VALUES ('2026-02-28T20:00:00', '2026-02-28T20:01:00', 'bidirectional', 'full', 'completed', ?)",
        (json.dumps({"added": 3, "removed": 0}),),
    )
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["db", "status"])
    assert result.exit_code == 0
    assert "1" in result.output  # track_mapping count
    assert "bidirectional" in result.output
    assert "completed" in result.output
    assert "added: 3" in result.output
