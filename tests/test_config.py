"""Tests for spondex.config module."""

from __future__ import annotations

import os
import stat
import tomllib
from pathlib import Path

import pytest

from spondex.config import (
    AppConfig,
    DaemonConfig,
    SyncConfig,
    _dump_toml,
    _format_toml_value,
    config_exists,
    ensure_dirs,
    load_config,
    save_config,
)


# ---------------------------------------------------------------------------
# 1. Default values
# ---------------------------------------------------------------------------


def test_daemon_config_defaults():
    cfg = DaemonConfig()
    assert cfg.dashboard_port == 9847
    assert cfg.log_level == "info"


def test_sync_config_defaults():
    cfg = SyncConfig()
    assert cfg.interval_minutes == 30
    assert cfg.mode == "incremental"


def test_app_config_defaults():
    cfg = AppConfig()
    assert cfg.daemon.dashboard_port == 9847
    assert cfg.daemon.log_level == "info"
    assert cfg.sync.interval_minutes == 30
    assert cfg.sync.mode == "incremental"


# ---------------------------------------------------------------------------
# 2. AppConfig properties (use base_dir fixture)
# ---------------------------------------------------------------------------


def test_base_dir_property(base_dir: Path):
    cfg = AppConfig()
    assert cfg.base_dir == base_dir


def test_socket_path(base_dir: Path):
    cfg = AppConfig()
    assert cfg.socket_path == base_dir / "daemon.sock"


def test_pid_path(base_dir: Path):
    cfg = AppConfig()
    assert cfg.pid_path == base_dir / "daemon.pid"


def test_log_dir(base_dir: Path):
    cfg = AppConfig()
    assert cfg.log_dir == base_dir / "logs"


# ---------------------------------------------------------------------------
# 3. ensure_dirs
# ---------------------------------------------------------------------------


def test_ensure_dirs_creates_directories(base_dir: Path, tmp_path: Path):
    # Point to a fresh subdirectory that does NOT exist yet so we can verify
    # ensure_dirs creates it from scratch.
    fresh = tmp_path / "fresh_base"
    # Overwrite the monkeypatch that base_dir already set, pointing to the
    # new location.  We import the module so we can patch the function object
    # in-place for the remainder of this test.
    import spondex.config as config_mod

    original = config_mod.get_base_dir
    config_mod.get_base_dir = lambda: fresh
    try:
        assert not fresh.exists()
        ensure_dirs()
        assert fresh.is_dir()
        assert (fresh / "logs").is_dir()
    finally:
        config_mod.get_base_dir = original


# ---------------------------------------------------------------------------
# 4. config_exists
# ---------------------------------------------------------------------------


def test_config_exists_false_when_missing(base_dir: Path):
    assert config_exists() is False


def test_config_exists_true_when_file_present(base_dir: Path):
    (base_dir / "config.toml").write_text("")
    assert config_exists() is True


# ---------------------------------------------------------------------------
# 5. save_config / load_config round-trip
# ---------------------------------------------------------------------------


def test_save_load_round_trip_defaults(base_dir: Path):
    original = AppConfig()
    save_config(original)
    loaded = load_config()

    assert loaded.daemon.dashboard_port == original.daemon.dashboard_port
    assert loaded.daemon.log_level == original.daemon.log_level
    assert loaded.sync.interval_minutes == original.sync.interval_minutes
    assert loaded.sync.mode == original.sync.mode


def test_save_load_round_trip_custom(base_dir: Path):
    original = AppConfig(
        daemon=DaemonConfig(dashboard_port=1234, log_level="debug"),
        sync=SyncConfig(interval_minutes=5, mode="full"),
    )
    save_config(original)
    loaded = load_config()

    assert loaded.daemon.dashboard_port == 1234
    assert loaded.daemon.log_level == "debug"
    assert loaded.sync.interval_minutes == 5
    assert loaded.sync.mode == "full"


# ---------------------------------------------------------------------------
# 6. load_config with no file returns defaults
# ---------------------------------------------------------------------------


def test_load_config_no_file_returns_defaults(base_dir: Path):
    cfg = load_config()
    default = AppConfig()

    assert cfg.daemon.dashboard_port == default.daemon.dashboard_port
    assert cfg.daemon.log_level == default.daemon.log_level
    assert cfg.sync.interval_minutes == default.sync.interval_minutes
    assert cfg.sync.mode == default.sync.mode


# ---------------------------------------------------------------------------
# 7. save_config sets chmod 600
# ---------------------------------------------------------------------------


def test_save_config_sets_permissions(base_dir: Path):
    save_config(AppConfig())
    config_path = base_dir / "config.toml"
    mode = stat.S_IMODE(os.stat(config_path).st_mode)
    assert mode == 0o600


# ---------------------------------------------------------------------------
# 8. _format_toml_value
# ---------------------------------------------------------------------------


def test_format_toml_value_string():
    assert _format_toml_value("hello") == '"hello"'


def test_format_toml_value_string_with_quotes():
    assert _format_toml_value('say "hi"') == '"say \\"hi\\""'


def test_format_toml_value_string_with_backslash():
    assert _format_toml_value("back\\slash") == '"back\\\\slash"'


def test_format_toml_value_int():
    assert _format_toml_value(42) == "42"


def test_format_toml_value_bool_true():
    assert _format_toml_value(True) == "true"


def test_format_toml_value_bool_false():
    assert _format_toml_value(False) == "false"


def test_format_toml_value_unsupported_type():
    with pytest.raises(TypeError, match="Unsupported TOML value type"):
        _format_toml_value([1, 2, 3])


# ---------------------------------------------------------------------------
# 9. _dump_toml round-trips through tomllib
# ---------------------------------------------------------------------------


def test_dump_toml_round_trips_defaults():
    cfg = AppConfig()
    toml_str = _dump_toml(cfg)
    parsed = tomllib.loads(toml_str)

    assert parsed["daemon"]["dashboard_port"] == cfg.daemon.dashboard_port
    assert parsed["daemon"]["log_level"] == cfg.daemon.log_level
    assert parsed["sync"]["interval_minutes"] == cfg.sync.interval_minutes
    assert parsed["sync"]["mode"] == cfg.sync.mode


def test_dump_toml_round_trips_custom():
    cfg = AppConfig(
        daemon=DaemonConfig(dashboard_port=8080, log_level="warning"),
        sync=SyncConfig(interval_minutes=1, mode="full"),
    )
    toml_str = _dump_toml(cfg)
    parsed = tomllib.loads(toml_str)

    assert parsed["daemon"]["dashboard_port"] == 8080
    assert parsed["daemon"]["log_level"] == "warning"
    assert parsed["sync"]["interval_minutes"] == 1
    assert parsed["sync"]["mode"] == "full"


def test_dump_toml_produces_valid_toml_structure():
    cfg = AppConfig()
    toml_str = _dump_toml(cfg)
    # Should contain section headers
    assert "[daemon]" in toml_str
    assert "[sync]" in toml_str
    # Should be parseable without error
    parsed = tomllib.loads(toml_str)
    assert "daemon" in parsed
    assert "sync" in parsed
