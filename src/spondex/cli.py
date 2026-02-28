"""CLI interface for the Spondex daemon."""

from __future__ import annotations

from collections import deque
from pathlib import Path

import httpx
import typer
from rich.console import Console

from spondex.config import get_base_dir, ensure_dirs

app = typer.Typer(
    name="spondex",
    help="CLI daemon for syncing music libraries between Yandex Music and Spotify.",
    add_completion=False,
)
console = Console()


# ---------------------------------------------------------------------------
# RPC helper
# ---------------------------------------------------------------------------


def _socket_path() -> Path:
    return get_base_dir() / "daemon.sock"


def send_command(cmd: str, params: dict | None = None) -> dict:
    """Send a JSON-RPC-style command to the running daemon over UDS.

    Raises a user-friendly error (via ``typer.Exit``) when the daemon
    socket does not exist or the connection is refused.
    """
    sock = _socket_path()
    if not sock.exists():
        console.print(
            "[red]Daemon is not running.[/red]  "
            "(socket not found at [bold]{path}[/bold])".format(path=sock),
        )
        raise typer.Exit(1)

    payload: dict = {"cmd": cmd}
    if params is not None:
        payload["params"] = params

    transport = httpx.HTTPTransport(uds=str(sock))
    try:
        with httpx.Client(transport=transport, base_url="http://localhost") as client:
            response = client.post("/rpc", json=payload, timeout=10.0)
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        console.print(
            "[red]Could not connect to daemon.[/red]  "
            "Is it running?  Try [bold]spondex start[/bold].",
        )
        raise typer.Exit(1)
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]Daemon returned an error:[/red] {exc.response.status_code}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def start() -> None:
    """Start the Spondex daemon."""
    from spondex.daemon import Daemon

    ensure_dirs()

    daemon = Daemon()
    if daemon.is_running():
        console.print("[yellow]Daemon is already running[/yellow] (PID {pid}).".format(pid=daemon.get_pid()))
        raise typer.Exit(0)

    daemon.start()
    console.print("[green]Daemon started[/green] (PID {pid}).".format(pid=daemon.get_pid()))


@app.command()
def stop() -> None:
    """Stop the Spondex daemon."""
    from spondex.daemon import Daemon

    # Try a graceful RPC shutdown first.
    sock = _socket_path()
    if sock.exists():
        try:
            send_command("shutdown")
            console.print("[green]Daemon stopped.[/green]")
            return
        except SystemExit:
            # send_command raises typer.Exit on connection errors — fall through
            # to the PID-based fallback.
            pass

    # Fallback: ask the Daemon helper to kill by PID file.
    daemon = Daemon()
    if not daemon.is_running():
        console.print("[yellow]Daemon is not running.[/yellow]")
        raise typer.Exit(0)

    daemon.stop()
    console.print("[green]Daemon stopped.[/green]")


@app.command()
def restart() -> None:
    """Restart the Spondex daemon (stop then start)."""
    from spondex.daemon import Daemon

    # --- stop phase ---
    sock = _socket_path()
    if sock.exists():
        try:
            send_command("shutdown")
        except SystemExit:
            pass

    daemon = Daemon()
    if daemon.is_running():
        daemon.stop()

    # --- start phase ---
    ensure_dirs()
    daemon = Daemon()
    daemon.start()
    console.print("[green]Daemon restarted[/green] (PID {pid}).".format(pid=daemon.get_pid()))


@app.command()
def status() -> None:
    """Show the current daemon status."""
    result = send_command("status")
    console.print_json(data=result)


@app.command()
def logs(
    tail_lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show"),
) -> None:
    """Show recent daemon log output."""
    log_file = get_base_dir() / "logs" / "daemon.log"
    if not log_file.exists():
        console.print("[yellow]Log file not found:[/yellow] {path}".format(path=log_file))
        raise typer.Exit(1)

    with open(log_file, "r", encoding="utf-8") as fh:
        # Use a bounded deque to efficiently read only the last N lines
        # without loading the entire file into memory.
        last_lines = deque(fh, maxlen=tail_lines)

    if not last_lines:
        console.print("[dim]Log file is empty.[/dim]")
        return

    for line in last_lines:
        console.print(line, end="", highlight=False)
