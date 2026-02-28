"""CLI interface for the Spondex daemon."""

from __future__ import annotations

from collections import deque
from pathlib import Path

import httpx
import typer
from rich.console import Console

from pydantic import SecretStr

from spondex.config import config_exists, ensure_dirs, get_base_dir, load_config, save_config

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

    if not config_exists():
        from spondex.wizard import run_wizard

        console.print("[yellow]No configuration found. Starting setup wizard...[/yellow]\n")
        cfg = run_wizard()
        save_config(cfg)
        console.print("[green]Configuration saved.[/green]\n")

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
def dashboard() -> None:
    """Open the web dashboard in the default browser."""
    import webbrowser

    cfg = load_config()
    url = f"http://127.0.0.1:{cfg.daemon.dashboard_port}"
    console.print(f"Opening dashboard at [bold]{url}[/bold]")
    webbrowser.open(url)


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


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _mask(secret: SecretStr) -> str:
    """Return '***' if the secret is non-empty, else '(not set)'."""
    return "[bold]***[/bold]" if secret.get_secret_value() else "[dim](not set)[/dim]"


@app.command(name="config")
def show_config() -> None:
    """Show current configuration (secrets are masked)."""
    cfg = load_config()

    console.print("\n[bold]Current Configuration[/bold]\n")

    console.print("[bold cyan]\\[daemon][/bold cyan]")
    console.print(f"  dashboard_port = {cfg.daemon.dashboard_port}")
    console.print(f"  log_level      = {cfg.daemon.log_level}")

    console.print("\n[bold cyan]\\[sync][/bold cyan]")
    console.print(f"  interval_minutes = {cfg.sync.interval_minutes}")
    console.print(f"  mode             = {cfg.sync.mode}")

    console.print("\n[bold cyan]\\[spotify][/bold cyan]")
    console.print(f"  client_id      = {cfg.spotify.client_id or '[dim](not set)[/dim]'}")
    console.print(f"  client_secret  = {_mask(cfg.spotify.client_secret)}")
    console.print(f"  redirect_uri   = {cfg.spotify.redirect_uri}")
    console.print(f"  refresh_token  = {_mask(cfg.spotify.refresh_token)}")

    console.print("\n[bold cyan]\\[yandex][/bold cyan]")
    console.print(f"  token = {_mask(cfg.yandex.token)}")
    console.print()


# ---------------------------------------------------------------------------
# Database inspection
# ---------------------------------------------------------------------------


db_app = typer.Typer(name="db", help="Database inspection commands.", add_completion=False)
app.add_typer(db_app)


@db_app.command(name="status")
def db_status() -> None:
    """Show database status and table statistics."""
    import sqlite3

    db_path = get_base_dir() / "spondex.db"
    if not db_path.exists():
        console.print("[yellow]Database not found.[/yellow] Start the daemon first to initialise it.")
        raise typer.Exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    console.print(f"\n[bold]Database[/bold]  {db_path}")
    size_kb = db_path.stat().st_size / 1024
    console.print(f"[dim]Size: {size_kb:.1f} KB[/dim]\n")

    tables = [
        ("track_mapping", "Track mappings (Spotify ↔ Yandex)"),
        ("collection", "Collections (liked / playlists)"),
        ("collection_track", "Tracks in collections"),
        ("unmatched", "Unmatched tracks"),
        ("sync_runs", "Sync runs"),
    ]

    for table, description in tables:
        cur = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}")  # noqa: S608
        count = cur.fetchone()["cnt"]
        style = "green" if count > 0 else "dim"
        console.print(f"  [{style}]{table:20s}[/{style}]  {count:>6}  [dim]{description}[/dim]")

    # Last sync run
    cur = conn.execute(
        "SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1"
    )
    last_run = cur.fetchone()
    if last_run:
        console.print("\n[bold]Last sync[/bold]")
        console.print(f"  Status:    {last_run['status']}")
        console.print(f"  Direction: {last_run['direction']}")
        console.print(f"  Mode:      {last_run['mode']}")
        console.print(f"  Started:   {last_run['started_at']}")
        if last_run["finished_at"]:
            console.print(f"  Finished:  {last_run['finished_at']}")
        if last_run["stats_json"]:
            import json
            stats = json.loads(last_run["stats_json"])
            parts = [f"{k}: {v}" for k, v in stats.items()]
            console.print(f"  Stats:     {', '.join(parts)}")
        if last_run["error_message"]:
            console.print(f"  [red]Error: {last_run['error_message']}[/red]")

    console.print()
