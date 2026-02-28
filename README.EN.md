# Spondex

CLI daemon for syncing music libraries between **Spotify** and **Yandex Music**.

Spondex runs as a background daemon, periodically synchronising liked tracks
between platforms. New likes on either side are automatically propagated to the
other, with fuzzy matching, transliteration, and duration validation.

## Installation

```bash
# Clone and install with uv
git clone <repo-url> && cd spondex
uv sync
```

## Prerequisites

Before the first `spondex start` you'll need credentials for both services. The setup wizard will ask for them interactively; below is how to obtain them in advance.

### Yandex Music Token

You can get an OAuth token via the browser (DevTools) or by following the guide:

- [Obtaining a Yandex Music token](https://yandex-music.readthedocs.io/en/main/token.html)

You can enter the token during the wizard or set it later:

```bash
spondex config set yandex.token <your_token>
```

### Spotify App Setup

1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/).
2. Create a new application (Create app).
3. Copy the **Client ID** and **Client Secret** from the app settings.
4. Under **Redirect URIs** add:
   - `http://127.0.0.1:8888/callback`
5. Save the changes.

On first launch the setup wizard will ask for Client ID and Client Secret, open a browser for Spotify OAuth, and save the `refresh_token` to `~/.spondex/config.toml`.

To set credentials manually:

```bash
spondex config set spotify.client_id <client_id>
spondex config set spotify.client_secret <client_secret>
spondex config set spotify.redirect_uri "http://127.0.0.1:8888/callback"
# refresh_token is issued after browser authorization (the wizard handles this automatically)
```

## Quick Start

```bash
# First launch — runs the setup wizard
spondex start

# Check status
spondex status

# Trigger an immediate sync
spondex sync --now

# View logs
spondex logs -f

# Open the web dashboard
spondex dashboard

# Stop the daemon
spondex stop
```

## Commands

| Command                          | Description                                      |
| -------------------------------- | ------------------------------------------------ |
| `spondex start`                  | Start the daemon (runs wizard on first launch)   |
| `spondex stop`                   | Stop the daemon gracefully                       |
| `spondex restart`                | Stop then start                                  |
| `spondex status`                 | Show state, uptime, scheduler info, track counts |
| `spondex sync [--mode full]`     | Trigger a sync cycle                             |
| `spondex logs [-n 50] [-f]`      | Show daemon log output                           |
| `spondex logs --sync`            | Show JSON sync log                               |
| `spondex dashboard`              | Open web dashboard in browser                    |
| `spondex config show`            | Show current configuration (secrets masked)      |
| `spondex config set <key> <val>` | Set a config value (e.g. `sync.mode full`)       |
| `spondex db status`              | Show database stats and last sync info           |

For detailed CLI documentation with all options and examples, see [docs/CLI.md](docs/CLI.md).

## Configuration

Configuration lives at `~/.spondex/config.toml` and is created by the setup
wizard on first `spondex start`.

```bash
# View
spondex config show

# Modify
spondex config set sync.interval_minutes 15
spondex config set sync.mode full
spondex config set spotify.refresh_token <token>
spondex config set yandex.token <token>
```

### Sections

- **daemon** — `dashboard_port`, `log_level`
- **sync** — `interval_minutes`, `mode` (full/incremental), `propagate_deletions`
- **spotify** — `client_id`, `client_secret`, `redirect_uri`, `refresh_token`
- **yandex** — `token`

## Architecture

```
CLI (typer)
  │
  │  httpx (UDS)
  ▼
FastAPI RPC Server ──► DaemonState
  │  ~/.spondex/daemon.sock       │
  │                               ├── SyncEngine
  │                               ├── SyncScheduler
  │                               └── Database (SQLite)
  │
Dashboard Server (Starlette + React SPA)
  │  http://127.0.0.1:9847
```

**CLI** — thin client that sends JSON commands over a Unix domain socket.

**Daemon** — double-fork daemonization with PID file, signal handling, and
structured logging (structlog → RotatingFileHandler).

**RPC Server** — FastAPI on UDS. All commands go through `POST /rpc` with
`{"cmd": "...", "params": {}}`.

**Sync Engine** — bidirectional sync with three-tier fuzzy matching (normalized,
transliterated, fuzzy with duration validation). Supports full and incremental
modes.

**Dashboard** — React SPA served by Starlette with real-time WebSocket updates,
charting, and track management.

## Development

```bash
# Install dev dependencies
uv sync --extra dev

# Run tests
uv run pytest tests/ -v

# Run tests with coverage
uv run pytest tests/ --cov=spondex --cov-report=term-missing

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/

# Type check
uv run mypy src/
```

## Security

- Config file (`~/.spondex/config.toml`) is created with `chmod 600`
- A warning is emitted if config permissions are too open
- Daemon sets `umask(0o077)` — all runtime files (socket, logs) are owner-only
- API tokens are stored as `SecretStr` and never appear in logs or CLI output
