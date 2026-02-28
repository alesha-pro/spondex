"""CLI interface for the Spondex daemon."""

from __future__ import annotations

from collections import deque
from datetime import UTC
from pathlib import Path

import httpx
import typer
from pydantic import SecretStr
from rich.console import Console

from spondex.config import config_exists, ensure_dirs, get_base_dir, load_config, save_config

app = typer.Typer(
    name="spondex",
    help="CLI daemon for syncing music libraries between Yandex Music and Spotify.",
    add_completion=False,
)
console = Console()


def main() -> None:
    """Entry point that wraps ``app()`` with a clean KeyboardInterrupt handler."""
    try:
        app()
    except KeyboardInterrupt:
        console.print("Interrupted.")
        raise SystemExit(130) from None


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
            f"[red]Daemon is not running.[/red]  (socket not found at [bold]{sock}[/bold])",
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
            "[red]Could not connect to daemon.[/red]  Is it running?  Try [bold]spondex start[/bold].",
        )
        raise typer.Exit(1) from None
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]Daemon returned an error:[/red] {exc.response.status_code}")
        raise typer.Exit(1) from exc


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_duration(seconds: float) -> str:
    """Format seconds into a human-readable duration string."""
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


def _human_time(iso_str: str | None) -> str:
    """Convert an ISO timestamp to a relative time string."""
    if not iso_str:
        return "—"
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        diff = (now - dt).total_seconds()
        if diff < 0:
            # Future
            abs_diff = abs(diff)
            if abs_diff < 60:
                return f"in {int(abs_diff)}s"
            if abs_diff < 3600:
                return f"in {int(abs_diff / 60)} min"
            return f"in {int(abs_diff / 3600)}h {int((abs_diff % 3600) / 60)}m"
        # Past
        if diff < 60:
            return f"{int(diff)}s ago"
        if diff < 3600:
            return f"{int(diff / 60)} min ago"
        return f"{int(diff / 3600)}h {int((diff % 3600) / 60)}m ago"
    except (ValueError, AttributeError):
        return iso_str


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def start() -> None:
    """Start the Spondex background daemon (runs setup wizard on first launch)."""
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
        console.print(f"[yellow]Daemon is already running[/yellow] (PID {daemon.get_pid()}).")
        raise typer.Exit(0)

    daemon.start()
    console.print(f"[green]Daemon started[/green] (PID {daemon.get_pid()}).")


@app.command()
def stop() -> None:
    """Stop the running daemon gracefully (falls back to SIGTERM if RPC unavailable)."""
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
    """Restart the daemon — performs stop followed by start."""
    import contextlib

    from spondex.daemon import Daemon

    # --- stop phase ---
    sock = _socket_path()
    if sock.exists():
        with contextlib.suppress(SystemExit):
            send_command("shutdown")

    daemon = Daemon()
    if daemon.is_running():
        daemon.stop()

    # --- start phase ---
    ensure_dirs()
    daemon = Daemon()
    daemon.start()
    console.print(f"[green]Daemon restarted[/green] (PID {daemon.get_pid()}).")


@app.command()
def dashboard() -> None:
    """Open the web dashboard in the default browser (http://127.0.0.1:<port>)."""
    import webbrowser

    cfg = load_config()
    url = f"http://127.0.0.1:{cfg.daemon.dashboard_port}"
    console.print(f"Opening dashboard at [bold]{url}[/bold]")
    webbrowser.open(url)


@app.command()
def sync(
    now: bool = typer.Option(True, "--now/--no-now", help="Trigger a sync immediately"),
    mode: str = typer.Option("", "--mode", "-m", help="Sync mode: full or incremental (default: daemon config)"),
) -> None:
    """Trigger a sync cycle on the running daemon."""
    if not now:
        console.print("[dim]Nothing to do (use --now to trigger sync).[/dim]")
        return
    params: dict = {}
    if mode:
        params["mode"] = mode
    result = send_command("sync_now", params=params if params else None)
    if result.get("ok", True):
        console.print("[green]Sync triggered.[/green]")
    else:
        console.print(f"[red]Error:[/red] {result.get('error', 'unknown')}")


@app.command()
def status() -> None:
    """Show daemon state, uptime, sync scheduler info, and track counters."""
    result = send_command("status")
    data = result.get("data", result) if isinstance(result, dict) else result

    console.print()

    # State
    sync_info = data.get("sync", {})
    state = sync_info.get("state", "unknown") if sync_info else "unknown"
    state_colors = {"idle": "green", "syncing": "blue", "paused": "yellow", "error": "red"}
    color = state_colors.get(state, "white")
    console.print(f"  [bold]State:[/bold]   [{color}]{state}[/{color}]")

    # Uptime
    uptime_secs = data.get("uptime_seconds")
    if uptime_secs is not None:
        console.print(f"  [bold]Uptime:[/bold]  {_format_duration(uptime_secs)}")

    # Scheduler
    sched = data.get("scheduler")
    if sched:
        console.print("\n  [bold cyan]Scheduler[/bold cyan]")
        if "mode" in sched:
            console.print(f"    mode:     {sched['mode']}")
        if "interval_minutes" in sched:
            console.print(f"    interval: {sched['interval_minutes']}m")
        if "paused" in sched:
            console.print(f"    paused:   {sched['paused']}")
        if sched.get("last_sync"):
            console.print(f"    last:     {_human_time(sched['last_sync'])}")
        if sched.get("next_sync"):
            console.print(f"    next:     {_human_time(sched['next_sync'])}")

    # Counters
    counts = data.get("counts")
    if counts:
        console.print("\n  [bold cyan]Counters[/bold cyan]")
        console.print(f"    tracks synced:  {counts.get('track_mappings', 0)}")
        console.print(f"    unmatched:      {counts.get('unmatched', 0)}")
        console.print(f"    sync runs:      {counts.get('sync_runs', 0)}")

    # Last sync stats
    if sync_info and sync_info.get("last_stats"):
        import json as _json

        try:
            stats = (
                _json.loads(sync_info["last_stats"])
                if isinstance(sync_info["last_stats"], str)
                else sync_info["last_stats"]
            )
            console.print("\n  [bold cyan]Last sync[/bold cyan]")
            for k, v in stats.items():
                console.print(f"    {k}: {v}")
        except (ValueError, TypeError):
            pass

    console.print()


@app.command()
def logs(
    tail_lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show"),
    sync: bool = typer.Option(False, "--sync", help="Show sync.log (JSON) instead of daemon.log"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output (like tail -f)"),
) -> None:
    """Show recent daemon log output (supports --sync for JSON sync log, --follow for live tail)."""
    filename = "sync.log" if sync else "daemon.log"
    log_file = get_base_dir() / "logs" / filename
    if not log_file.exists():
        console.print(f"[yellow]Log file not found:[/yellow] {log_file}")
        raise typer.Exit(1)

    if follow:
        _follow_log(log_file, tail_lines)
        return

    with open(log_file, encoding="utf-8") as fh:
        # Use a bounded deque to efficiently read only the last N lines
        # without loading the entire file into memory.
        last_lines = deque(fh, maxlen=tail_lines)

    if not last_lines:
        console.print("[dim]Log file is empty.[/dim]")
        return

    for line in last_lines:
        _print_log_line(line)


def _log_line_style(line: str) -> str | None:
    """Return a Rich style string based on the log level found in *line*.

    Matches structlog formats only:
    - ConsoleRenderer: ``[error    ]``
    - JSONRenderer: ``"level": "error"``
    """
    lower = line.lower()
    if "[error" in lower or "[critical" in lower or '"level": "error"' in lower or '"level": "critical"' in lower:
        return "red"
    if "[warning" in lower or '"level": "warning"' in lower:
        return "yellow"
    if "[debug" in lower or '"level": "debug"' in lower:
        return "dim"
    return None


def _print_log_line(line: str) -> None:
    """Print a single log line with level-based color highlighting."""
    line = line.rstrip("\n")
    if not line:
        return
    console.print(line, style=_log_line_style(line), highlight=False, markup=False)


def _follow_log(log_file: Path, initial_lines: int = 10) -> None:
    """Follow a log file, printing new lines as they appear (like ``tail -f``)."""
    import time

    # Show last N lines first.
    with open(log_file, encoding="utf-8") as fh:
        last = deque(fh, maxlen=initial_lines)
    for line in last:
        _print_log_line(line)

    # Then follow new output.
    with open(log_file, encoding="utf-8") as fh:
        fh.seek(0, 2)  # seek to end
        try:
            while True:
                line = fh.readline()
                if line:
                    _print_log_line(line)
                else:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            pass


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _mask(secret: SecretStr) -> str:
    """Return '***' if the secret is non-empty, else '(not set)'."""
    return "[bold]***[/bold]" if secret.get_secret_value() else "[dim](not set)[/dim]"


config_app = typer.Typer(name="config", help="View and modify configuration.", add_completion=False)
app.add_typer(config_app)


@config_app.command(name="show")
def config_show() -> None:
    """Show current configuration (secrets are masked)."""
    cfg = load_config()

    console.print("\n[bold]Current Configuration[/bold]\n")

    console.print("[bold cyan]\\[daemon][/bold cyan]")
    console.print(f"  dashboard_port = {cfg.daemon.dashboard_port}")
    console.print(f"  log_level      = {cfg.daemon.log_level}")

    console.print("\n[bold cyan]\\[sync][/bold cyan]")
    console.print(f"  interval_minutes = {cfg.sync.interval_minutes}")
    console.print(f"  mode             = {cfg.sync.mode}")
    console.print(f"  propagate_deletions = {cfg.sync.propagate_deletions}")

    console.print("\n[bold cyan]\\[spotify][/bold cyan]")
    console.print(f"  client_id      = {cfg.spotify.client_id or '[dim](not set)[/dim]'}")
    console.print(f"  client_secret  = {_mask(cfg.spotify.client_secret)}")
    console.print(f"  redirect_uri   = {cfg.spotify.redirect_uri}")
    console.print(f"  refresh_token  = {_mask(cfg.spotify.refresh_token)}")

    console.print("\n[bold cyan]\\[yandex][/bold cyan]")
    console.print(f"  token = {_mask(cfg.yandex.token)}")
    console.print()


@config_app.command(name="set")
def config_set(
    key: str = typer.Argument(help="Dotted key, e.g. sync.interval_minutes"),
    value: str = typer.Argument(help="New value"),
) -> None:
    """Set a configuration value (e.g. spondex config set sync.interval_minutes 15)."""

    parts = key.split(".", maxsplit=1)
    if len(parts) != 2:
        console.print("[red]Key must be in section.field format (e.g. sync.mode).[/red]")
        raise typer.Exit(1)

    section_name, field_name = parts

    cfg = load_config()
    section_map = {
        "daemon": cfg.daemon,
        "sync": cfg.sync,
        "spotify": cfg.spotify,
        "yandex": cfg.yandex,
    }

    if section_name not in section_map:
        console.print(f"[red]Unknown section:[/red] {section_name}")
        console.print(f"[dim]Valid sections: {', '.join(section_map)}[/dim]")
        raise typer.Exit(1)

    section_model = section_map[section_name]
    fields = type(section_model).model_fields
    if field_name not in fields:
        console.print(f"[red]Unknown field:[/red] {section_name}.{field_name}")
        console.print(f"[dim]Valid fields: {', '.join(fields)}[/dim]")
        raise typer.Exit(1)

    field_info = fields[field_name]
    field_type = field_info.annotation

    # Coerce the value to the correct type
    try:
        coerced = _coerce_value(value, field_type)
    except (ValueError, TypeError) as exc:
        console.print(f"[red]Invalid value:[/red] {exc}")
        raise typer.Exit(1) from exc

    # Rebuild the section with the updated value
    section_data = section_model.model_dump(mode="python")
    section_data[field_name] = coerced

    new_section = type(section_model)(**section_data)
    setattr(cfg, section_name, new_section)
    save_config(cfg)

    # Display confirmation (mask secrets)
    display_val = "***" if isinstance(coerced, SecretStr) else coerced
    console.print(f"[green]Set[/green] {key} = {display_val}")


def _coerce_value(raw: str, field_type: type) -> object:
    """Coerce a string value to the expected field type."""
    import typing

    origin = typing.get_origin(field_type)
    args = typing.get_args(field_type)

    if field_type is SecretStr:
        return SecretStr(raw)

    if field_type is bool:
        if raw.lower() in ("true", "1", "yes"):
            return True
        if raw.lower() in ("false", "0", "no"):
            return False
        msg = f"Cannot convert '{raw}' to bool (use true/false)"
        raise ValueError(msg)

    if field_type is int:
        return int(raw)

    if field_type is str:
        return raw

    # Handle Literal types
    if origin is typing.Literal:
        if raw not in args:
            msg = f"'{raw}' is not a valid option (choose from: {', '.join(str(a) for a in args)})"
            raise ValueError(msg)
        return raw

    return raw


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
    cur = conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1")
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
