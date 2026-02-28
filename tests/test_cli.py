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

    with patch("spondex.daemon.Daemon.is_running", return_value=False):
        result = runner.invoke(app, ["stop"])

    assert result.exit_code == 0
    assert "not running" in result.output.lower()


# ---------------------------------------------------------------------------
# 4. logs when no log file exists
# ---------------------------------------------------------------------------


def test_logs_no_log_file(cli_base_dir: Path):
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
    (cli_base_dir / "config.toml").write_text('[daemon]\nlog_level = "info"\n')

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
    (cli_base_dir / "config.toml").write_text('[daemon]\nlog_level = "info"\n')

    with (
        patch("spondex.wizard.run_wizard") as mock_wizard,
        patch("spondex.daemon.Daemon.is_running", return_value=True),
        patch("spondex.daemon.Daemon.get_pid", return_value=42),
    ):
        result = runner.invoke(app, ["start"])

    mock_wizard.assert_not_called()
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 8. config show command
# ---------------------------------------------------------------------------


def test_config_shows_sections(cli_base_dir: Path):
    """config show displays all sections with masked secrets."""
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

    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "test-id" in result.output
    assert "***" in result.output
    assert "secret" not in result.output.lower().replace("client_secret", "")
    assert "ym-tok" not in result.output


def test_config_empty_secrets_show_not_set(cli_base_dir: Path):
    """config show shows '(not set)' for empty secrets."""
    from spondex.config import AppConfig, save_config

    save_config(AppConfig())

    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "not set" in result.output


# ---------------------------------------------------------------------------
# 8b. config set command
# ---------------------------------------------------------------------------


def test_config_set_int(cli_base_dir: Path):
    """config set changes an integer field."""
    from spondex.config import AppConfig, load_config, save_config

    save_config(AppConfig())

    result = runner.invoke(app, ["config", "set", "sync.interval_minutes", "15"])
    assert result.exit_code == 0
    assert "15" in result.output

    cfg = load_config()
    assert cfg.sync.interval_minutes == 15


def test_config_set_str(cli_base_dir: Path):
    """config set changes a string field."""
    from spondex.config import AppConfig, load_config, save_config

    save_config(AppConfig())

    result = runner.invoke(app, ["config", "set", "daemon.log_level", "debug"])
    assert result.exit_code == 0
    assert "debug" in result.output

    cfg = load_config()
    assert cfg.daemon.log_level == "debug"


def test_config_set_bool(cli_base_dir: Path):
    """config set changes a boolean field."""
    from spondex.config import AppConfig, load_config, save_config

    save_config(AppConfig())

    result = runner.invoke(app, ["config", "set", "sync.propagate_deletions", "false"])
    assert result.exit_code == 0
    assert "False" in result.output

    cfg = load_config()
    assert cfg.sync.propagate_deletions is False


def test_config_set_literal(cli_base_dir: Path):
    """config set changes a Literal field."""
    from spondex.config import AppConfig, load_config, save_config

    save_config(AppConfig())

    result = runner.invoke(app, ["config", "set", "sync.mode", "full"])
    assert result.exit_code == 0
    assert "full" in result.output

    cfg = load_config()
    assert cfg.sync.mode == "full"


def test_config_set_secret(cli_base_dir: Path):
    """config set masks SecretStr in output."""
    from spondex.config import AppConfig, load_config, save_config

    save_config(AppConfig())

    result = runner.invoke(app, ["config", "set", "yandex.token", "my-secret-token"])
    assert result.exit_code == 0
    assert "***" in result.output
    assert "my-secret-token" not in result.output

    cfg = load_config()
    assert cfg.yandex.token.get_secret_value() == "my-secret-token"


def test_config_set_invalid_section(cli_base_dir: Path):
    """config set rejects unknown section."""
    from spondex.config import AppConfig, save_config

    save_config(AppConfig())

    result = runner.invoke(app, ["config", "set", "nonexistent.field", "val"])
    assert result.exit_code == 1
    assert "unknown section" in result.output.lower()


def test_config_set_invalid_field(cli_base_dir: Path):
    """config set rejects unknown field."""
    from spondex.config import AppConfig, save_config

    save_config(AppConfig())

    result = runner.invoke(app, ["config", "set", "daemon.nonexistent", "val"])
    assert result.exit_code == 1
    assert "unknown field" in result.output.lower()


def test_config_set_invalid_value(cli_base_dir: Path):
    """config set rejects bad int value."""
    from spondex.config import AppConfig, save_config

    save_config(AppConfig())

    result = runner.invoke(app, ["config", "set", "sync.interval_minutes", "abc"])
    assert result.exit_code == 1
    assert "invalid" in result.output.lower()


def test_config_set_invalid_literal(cli_base_dir: Path):
    """config set rejects invalid literal option."""
    from spondex.config import AppConfig, save_config

    save_config(AppConfig())

    result = runner.invoke(app, ["config", "set", "sync.mode", "turbo"])
    assert result.exit_code == 1
    assert "not a valid option" in result.output.lower() or "invalid" in result.output.lower()


def test_config_set_bad_key_format(cli_base_dir: Path):
    """config set rejects keys without dot separator."""
    from spondex.config import AppConfig, save_config

    save_config(AppConfig())

    result = runner.invoke(app, ["config", "set", "nodot", "val"])
    assert result.exit_code == 1
    assert "section.field" in result.output.lower()


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

    conn.execute("INSERT INTO track_mapping (spotify_id, artist, title) VALUES ('sp1', 'Artist', 'Song')")
    conn.execute(
        "INSERT INTO sync_runs (started_at, finished_at, direction, mode, status, stats_json) "
        "VALUES ('2026-02-28T20:00:00', '2026-02-28T20:01:00', 'bidirectional', 'full', 'completed', ?)",
        (json.dumps({"added": 3, "removed": 0}),),
    )
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["db", "status"])
    assert result.exit_code == 0
    assert "1" in result.output
    assert "bidirectional" in result.output
    assert "completed" in result.output
    assert "added: 3" in result.output


# ---------------------------------------------------------------------------
# 10. sync command
# ---------------------------------------------------------------------------


def test_sync_now_daemon_not_running(cli_base_dir: Path):
    """sync command reports daemon not running when no socket."""
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 1
    assert "not running" in result.output.lower() or "daemon" in result.output.lower()


def test_sync_now_success(cli_base_dir: Path):
    """sync --now triggers sync via RPC."""
    with patch("spondex.cli.send_command", return_value={"ok": True, "data": {"message": "sync triggered"}}) as mock:
        result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    assert "triggered" in result.output.lower()
    mock.assert_called_once_with("sync_now", params=None)


def test_sync_with_mode(cli_base_dir: Path):
    """sync --mode full passes mode to RPC."""
    with patch("spondex.cli.send_command", return_value={"ok": True, "data": {}}) as mock:
        result = runner.invoke(app, ["sync", "--mode", "full"])

    assert result.exit_code == 0
    mock.assert_called_once_with("sync_now", params={"mode": "full"})


def test_sync_error(cli_base_dir: Path):
    """sync shows error message on failure."""
    with patch("spondex.cli.send_command", return_value={"ok": False, "error": "sync not configured"}):
        result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    assert "error" in result.output.lower() or "not configured" in result.output.lower()


# ---------------------------------------------------------------------------
# 11. status formatted output
# ---------------------------------------------------------------------------


def test_status_formatted_output(cli_base_dir: Path):
    """status shows formatted output instead of raw JSON."""
    mock_data = {
        "ok": True,
        "data": {
            "uptime_seconds": 330.5,
            "started_at": "2026-03-01T00:00:00+00:00",
            "sync": {
                "state": "idle",
                "last_stats": '{"sp_added": 5, "ym_added": 3}',
            },
            "scheduler": {
                "mode": "incremental",
                "interval_minutes": 30,
                "paused": False,
            },
            "counts": {
                "track_mappings": 150,
                "unmatched": 12,
                "sync_runs": 8,
            },
        },
    }
    with patch("spondex.cli.send_command", return_value=mock_data):
        result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "idle" in result.output
    assert "5m" in result.output
    assert "150" in result.output
    assert "12" in result.output


# ---------------------------------------------------------------------------
# 12. KeyboardInterrupt handling
# ---------------------------------------------------------------------------


def test_keyboard_interrupt_handling():
    """main() catches KeyboardInterrupt and exits with code 130."""
    from spondex.cli import main

    with patch("spondex.cli.app", side_effect=KeyboardInterrupt), pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 130


# ---------------------------------------------------------------------------
# 13. _format_duration helper
# ---------------------------------------------------------------------------


def test_format_duration():
    """_format_duration returns human-readable durations."""
    from spondex.cli import _format_duration

    assert _format_duration(45) == "45s"
    assert _format_duration(90) == "1m 30s"
    assert _format_duration(3661) == "1h 1m"
    assert _format_duration(90000) == "1d 1h"


# ---------------------------------------------------------------------------
# 14. _human_time helper
# ---------------------------------------------------------------------------


def test_human_time_none():
    """_human_time returns dash for None."""
    from spondex.cli import _human_time

    assert _human_time(None) == "\u2014"


def test_human_time_invalid():
    """_human_time returns raw string for unparseable input."""
    from spondex.cli import _human_time

    assert _human_time("not-a-date") == "not-a-date"
