"""Tests for spondex.daemon — Daemon lifecycle and socket helpers."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from spondex.daemon import Daemon, ensure_clean_socket


# ---------------------------------------------------------------------------
# Daemon.__init__
# ---------------------------------------------------------------------------


class TestDaemonInit:
    """Daemon.__init__ derives paths correctly from base_dir."""

    def test_paths_derived_from_base_dir(self, base_dir: Path) -> None:
        d = Daemon()

        assert d.base_dir == base_dir
        assert d.pid_path == base_dir / "daemon.pid"
        assert d.socket_path == base_dir / "daemon.sock"
        assert d.log_dir == base_dir / "logs"
        assert d.log_file == base_dir / "logs" / "daemon.log"

    def test_shutdown_event_initially_none(self, base_dir: Path) -> None:
        d = Daemon()
        assert d._shutdown_event is None


# ---------------------------------------------------------------------------
# Daemon.get_pid
# ---------------------------------------------------------------------------


class TestGetPid:
    """Daemon.get_pid reads or returns None."""

    def test_returns_none_when_no_pid_file(self, base_dir: Path) -> None:
        d = Daemon()
        assert d.get_pid() is None

    def test_returns_int_when_pid_file_exists(self, base_dir: Path) -> None:
        d = Daemon()
        d.pid_path.write_text("12345")
        assert d.get_pid() == 12345

    def test_returns_none_for_invalid_content(self, base_dir: Path) -> None:
        d = Daemon()
        d.pid_path.write_text("not-a-number")
        assert d.get_pid() is None


# ---------------------------------------------------------------------------
# Daemon.is_running
# ---------------------------------------------------------------------------


class TestIsRunning:
    """Daemon.is_running checks process liveness."""

    def test_returns_false_when_no_pid_file(self, base_dir: Path) -> None:
        d = Daemon()
        assert d.is_running() is False

    def test_stale_pid_returns_false_and_cleans_up(self, base_dir: Path) -> None:
        d = Daemon()
        # Use a PID that almost certainly does not exist.
        d.pid_path.write_text("99999999")
        assert d.pid_path.exists()

        assert d.is_running() is False
        # The stale PID file should have been removed.
        assert not d.pid_path.exists()


# ---------------------------------------------------------------------------
# Daemon._write_pid
# ---------------------------------------------------------------------------


class TestWritePid:
    """Daemon._write_pid persists the current PID."""

    def test_writes_current_pid(self, base_dir: Path) -> None:
        d = Daemon()
        d._write_pid()

        assert d.pid_path.exists()
        assert int(d.pid_path.read_text().strip()) == os.getpid()


# ---------------------------------------------------------------------------
# Daemon._cleanup
# ---------------------------------------------------------------------------


class TestCleanup:
    """Daemon._cleanup removes PID and socket files."""

    def test_removes_pid_and_socket_files(self, base_dir: Path) -> None:
        d = Daemon()
        d.pid_path.write_text("12345")
        d.socket_path.touch()

        d._cleanup()

        assert not d.pid_path.exists()
        assert not d.socket_path.exists()

    def test_no_error_when_files_missing(self, base_dir: Path) -> None:
        d = Daemon()
        # Neither file exists — should not raise.
        d._cleanup()


# ---------------------------------------------------------------------------
# ensure_clean_socket
# ---------------------------------------------------------------------------


class TestEnsureCleanSocket:
    """ensure_clean_socket removes stale sockets and ignores absent paths."""

    def test_noop_when_path_does_not_exist(self, tmp_path: Path) -> None:
        sock_path = tmp_path / "nonexistent.sock"
        # Should return without error.
        ensure_clean_socket(sock_path)
        assert not sock_path.exists()

    def test_removes_stale_unix_socket(self) -> None:
        import tempfile

        # Use a short temp directory to stay under the 104-byte AF_UNIX
        # path limit on macOS.
        with tempfile.TemporaryDirectory(dir="/tmp") as short_dir:
            sock_path = Path(short_dir) / "s.sock"

            # Create a real Unix domain socket, then close it so it
            # becomes stale.
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                s.bind(str(sock_path))
            finally:
                s.close()

            assert sock_path.exists()

            ensure_clean_socket(sock_path)

            assert not sock_path.exists()
