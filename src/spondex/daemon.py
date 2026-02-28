"""Daemon management for the Spondex background process.

Handles daemonization (double-fork), PID tracking, graceful shutdown, and
the async main loop that hosts the JSON-RPC server over a Unix domain socket.
"""

from __future__ import annotations

import asyncio
import atexit
import os
import signal
import socket
import sys
import time
from pathlib import Path

import structlog
import uvicorn

from spondex.config import get_base_dir

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants derived from the shared config layout
# ---------------------------------------------------------------------------

_PID_FILE = "daemon.pid"
_SOCKET_FILE = "daemon.sock"
_LOG_DIR = "logs"
_DAEMON_LOG = "daemon.log"


# ---------------------------------------------------------------------------
# Standalone helpers
# ---------------------------------------------------------------------------


def ensure_clean_socket(sock_path: Path) -> None:
    """Remove *sock_path* if it is a stale (unconnectable) Unix socket.

    If a living process is listening on the socket the file is left alone so
    that we don't accidentally break a running daemon.
    """
    if not sock_path.exists():
        return

    # Try to connect — if we can, somebody is already listening.
    test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        test_sock.connect(str(sock_path))
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        # Nobody home — safe to remove the leftover file.
        log.debug("removing stale socket", path=str(sock_path))
        sock_path.unlink(missing_ok=True)
    else:
        test_sock.close()


# ---------------------------------------------------------------------------
# Daemon class
# ---------------------------------------------------------------------------


class Daemon:
    """Manages the lifecycle of the Spondex background daemon."""

    def __init__(self) -> None:
        base = get_base_dir()
        self.base_dir: Path = base
        self.pid_path: Path = base / _PID_FILE
        self.socket_path: Path = base / _SOCKET_FILE
        self.log_dir: Path = base / _LOG_DIR
        self.log_file: Path = self.log_dir / _DAEMON_LOG

        self._shutdown_event: asyncio.Event | None = None

    # -- PID helpers --------------------------------------------------------

    def get_pid(self) -> int | None:
        """Read the PID from the PID file, or *None* if it does not exist."""
        try:
            return int(self.pid_path.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None

    def is_running(self) -> bool:
        """Return *True* if the daemon process is alive.

        Cleans up a stale PID file when the recorded process no longer exists.
        """
        pid = self.get_pid()
        if pid is None:
            return False

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            # Process is gone — clean up the stale PID file.
            log.debug("removing stale pid file", pid=pid)
            self.pid_path.unlink(missing_ok=True)
            return False
        except PermissionError:
            # Process exists but we lack permission to signal it — still alive.
            return True

        return True

    def _write_pid(self) -> None:
        """Write the current process PID to the PID file."""
        self.pid_path.write_text(str(os.getpid()))

    def _cleanup(self) -> None:
        """Remove the PID file and socket file if they exist."""
        self.pid_path.unlink(missing_ok=True)
        self.socket_path.unlink(missing_ok=True)

    # -- Start / Stop -------------------------------------------------------

    def start(self) -> None:  # noqa: C901
        """Daemonize the current process using the classic double-fork.

        After daemonization the process runs :meth:`_run_daemon` and never
        returns to the caller in the child; the *parent* returns immediately
        after the first fork so that the CLI can print a confirmation message.
        """
        if self.is_running():
            log.warning("daemon already running", pid=self.get_pid())
            return

        # Ensure runtime directories exist.
        self.base_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        # -- first fork -------------------------------------------------------
        try:
            pid = os.fork()
        except OSError as exc:
            log.error("first fork failed", error=str(exc))
            sys.exit(1)

        if pid > 0:
            # Parent — wait briefly for the grandchild to write its PID file,
            # then return control to the CLI.
            for _ in range(50):
                if self.pid_path.exists():
                    break
                time.sleep(0.1)
            return

        # -- child: new session ------------------------------------------------
        os.setsid()

        # -- second fork -------------------------------------------------------
        try:
            pid = os.fork()
        except OSError as exc:
            log.error("second fork failed", error=str(exc))
            sys.exit(1)

        if pid > 0:
            # First child exits; grandchild continues.
            os._exit(0)

        # -- grandchild: the actual daemon process -----------------------------

        # Redirect standard file descriptors.
        sys.stdout.flush()
        sys.stderr.flush()

        devnull = open(os.devnull, "rb")  # noqa: SIM115
        log_fh = open(self.log_file, "ab")  # noqa: SIM115

        os.dup2(devnull.fileno(), sys.stdin.fileno())
        os.dup2(log_fh.fileno(), sys.stdout.fileno())
        os.dup2(log_fh.fileno(), sys.stderr.fileno())

        # Write PID and register cleanup.
        self._write_pid()
        atexit.register(self._cleanup)

        self._run_daemon()

    def stop(self) -> None:
        """Send SIGTERM to the running daemon and wait for it to exit."""
        pid = self.get_pid()
        if pid is None:
            log.info("no pid file found; daemon is not running")
            return

        if not self.is_running():
            log.info("daemon is not running (stale pid file cleaned up)")
            return

        log.info("sending SIGTERM to daemon", pid=pid)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            log.info("process already gone", pid=pid)
            self._cleanup()
            return

        # Wait for the process to exit (up to 10 seconds).
        for _ in range(100):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                log.info("daemon stopped", pid=pid)
                self._cleanup()
                return
            time.sleep(0.1)

        log.warning("daemon did not stop in time; sending SIGKILL", pid=pid)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self._cleanup()

    # -- Internal daemon loop -----------------------------------------------

    def _run_daemon(self) -> None:
        """Start the async main loop.

        Called inside the fully daemonized grandchild process.
        """
        asyncio.run(self._async_main())

    async def _async_main(self) -> None:
        """Async entry point: start the RPC server and wait for shutdown."""
        from spondex.config import load_config
        from spondex.server.dashboard import create_dashboard_app
        from spondex.server.rpc import DaemonState, create_rpc_app
        from spondex.storage import Database
        from spondex.sync.engine import SyncEngine
        from spondex.sync.scheduler import SyncScheduler

        state = DaemonState()
        app_config = load_config()

        # Initialise the database.
        db = Database(self.base_dir / "spondex.db")
        await db.connect()

        state.db = db

        # Initialise sync engine and scheduler.
        engine = SyncEngine(app_config, db)
        scheduler = SyncScheduler(
            engine,
            interval_minutes=app_config.sync.interval_minutes,
            default_mode=app_config.sync.mode,
        )
        state.engine = engine
        state.scheduler = scheduler

        if app_config.is_spotify_configured() and app_config.is_yandex_configured():
            await scheduler.start()

        # Install signal handlers via the event loop so they can safely
        # set the asyncio.Event.
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, state.request_shutdown)

        ensure_clean_socket(self.socket_path)

        # RPC server on Unix domain socket.
        rpc_app = create_rpc_app(state)
        rpc_config = uvicorn.Config(
            rpc_app,
            uds=str(self.socket_path),
            log_level="info",
            loop="asyncio",
        )
        rpc_server = uvicorn.Server(rpc_config)

        # Dashboard server on TCP.
        dashboard_app = create_dashboard_app(state, db)
        dashboard_config = uvicorn.Config(
            dashboard_app,
            host="127.0.0.1",
            port=app_config.daemon.dashboard_port,
            log_level="info",
            loop="asyncio",
        )
        dashboard_server = uvicorn.Server(dashboard_config)

        # Run both servers in background tasks.
        rpc_task = asyncio.create_task(rpc_server.serve())
        dashboard_task = asyncio.create_task(dashboard_server.serve())

        # Wait until we receive a termination signal or RPC shutdown.
        await state.shutdown_event.wait()

        log.info("initiating graceful shutdown")

        # Stop scheduler (waits for in-progress sync).
        await scheduler.stop()

        rpc_server.should_exit = True
        dashboard_server.should_exit = True
        await rpc_task
        await dashboard_task

        # Close the database.
        await db.close()

        # Final cleanup.
        self._cleanup()
        log.info("daemon shut down cleanly")
