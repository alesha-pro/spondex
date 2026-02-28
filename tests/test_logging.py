"""Tests for the structured logging configuration."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest
import structlog

from spondex.logging import setup_logging


@pytest.fixture(autouse=True)
def _reset_logging():
    """Reset logging state between tests."""
    yield
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)
    structlog.reset_defaults()


# -- File creation ----------------------------------------------------------


def test_setup_creates_log_dir_and_files(tmp_path: Path):
    log_dir = tmp_path / "logs"
    setup_logging(log_level="info", log_dir=log_dir)

    log = structlog.get_logger("spondex.test")
    log.info("hello")

    assert log_dir.exists()
    assert (log_dir / "daemon.log").exists()


# -- daemon.log format -----------------------------------------------------


def test_daemon_log_human_readable(tmp_path: Path):
    log_dir = tmp_path / "logs"
    setup_logging(log_level="info", log_dir=log_dir)

    log = structlog.get_logger("spondex.daemon")
    log.info("test_event", key="value")

    content = (log_dir / "daemon.log").read_text()
    assert "test_event" in content
    # ConsoleRenderer uses key=value format
    assert "key=value" in content


def test_daemon_log_not_json(tmp_path: Path):
    log_dir = tmp_path / "logs"
    setup_logging(log_level="info", log_dir=log_dir)

    log = structlog.get_logger("spondex.daemon")
    log.info("check_format")

    content = (log_dir / "daemon.log").read_text().strip()
    with pytest.raises(json.JSONDecodeError):
        json.loads(content)


# -- sync.log format -------------------------------------------------------


def test_sync_log_json(tmp_path: Path):
    log_dir = tmp_path / "logs"
    setup_logging(log_level="info", log_dir=log_dir)

    log = structlog.get_logger("spondex.sync.engine")
    log.info("sync_start", mode="full")

    content = (log_dir / "sync.log").read_text().strip()
    data = json.loads(content)
    assert data["event"] == "sync_start"
    assert data["mode"] == "full"
    assert data["level"] == "info"


def test_sync_log_contains_timestamp(tmp_path: Path):
    log_dir = tmp_path / "logs"
    setup_logging(log_level="info", log_dir=log_dir)

    log = structlog.get_logger("spondex.sync.engine")
    log.info("ts_check")

    data = json.loads((log_dir / "sync.log").read_text().strip())
    assert "timestamp" in data


# -- Filtering --------------------------------------------------------------


def test_sync_log_excludes_non_sync_events(tmp_path: Path):
    log_dir = tmp_path / "logs"
    setup_logging(log_level="info", log_dir=log_dir)

    structlog.get_logger("spondex.daemon").info("daemon_event")
    structlog.get_logger("spondex.sync.engine").info("sync_event")

    sync_content = (log_dir / "sync.log").read_text()
    assert "sync_event" in sync_content
    assert "daemon_event" not in sync_content


def test_daemon_log_contains_all_events(tmp_path: Path):
    log_dir = tmp_path / "logs"
    setup_logging(log_level="info", log_dir=log_dir)

    structlog.get_logger("spondex.daemon").info("from_daemon")
    structlog.get_logger("spondex.sync.engine").info("from_sync")

    daemon_content = (log_dir / "daemon.log").read_text()
    assert "from_daemon" in daemon_content
    assert "from_sync" in daemon_content


# -- Log level filtering ----------------------------------------------------


def test_level_filtering_suppresses_lower(tmp_path: Path):
    log_dir = tmp_path / "logs"
    setup_logging(log_level="warning", log_dir=log_dir)

    log = structlog.get_logger("spondex.test")
    log.info("should_not_appear")
    log.warning("should_appear")

    content = (log_dir / "daemon.log").read_text()
    assert "should_not_appear" not in content
    assert "should_appear" in content


def test_debug_level_includes_debug(tmp_path: Path):
    log_dir = tmp_path / "logs"
    setup_logging(log_level="debug", log_dir=log_dir)

    log = structlog.get_logger("spondex.test")
    log.debug("debug_msg")

    content = (log_dir / "daemon.log").read_text()
    assert "debug_msg" in content


# -- RotatingFileHandler config --------------------------------------------


def test_rotation_parameters(tmp_path: Path):
    log_dir = tmp_path / "logs"
    setup_logging(log_level="info", log_dir=log_dir)

    root = logging.getLogger()
    rotating = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
    assert len(rotating) == 2

    for handler in rotating:
        assert handler.maxBytes == 10 * 1024 * 1024
        assert handler.backupCount == 5


# -- No log_dir (no file handlers) -----------------------------------------


def test_no_log_dir_no_handlers(tmp_path: Path):
    setup_logging(log_level="info", log_dir=None)

    root = logging.getLogger()
    assert len(root.handlers) == 0


# -- Context variables -----------------------------------------------------


def test_context_variables_in_sync_log(tmp_path: Path):
    log_dir = tmp_path / "logs"
    setup_logging(log_level="info", log_dir=log_dir)

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service="spotify", operation="fetch_likes")

    log = structlog.get_logger("spondex.sync.engine")
    log.info("with_context")

    structlog.contextvars.clear_contextvars()

    data = json.loads((log_dir / "sync.log").read_text().strip())
    assert data["service"] == "spotify"
    assert data["operation"] == "fetch_likes"
