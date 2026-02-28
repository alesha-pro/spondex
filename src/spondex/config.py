"""Configuration management for the Spondex daemon."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BASE_DIR_NAME = ".spondex"
_CONFIG_FILE = "config.toml"
_PID_FILE = "daemon.pid"
_SOCKET_FILE = "daemon.sock"
_LOG_DIR = "logs"


def get_base_dir() -> Path:
    """Return the base directory for all Spondex runtime files (~/.spondex/)."""
    return Path.home() / _BASE_DIR_NAME


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------


class DaemonConfig(BaseModel):
    """Settings that control the daemon process itself."""

    dashboard_port: int = Field(default=9847, description="Port for the web dashboard")
    log_level: str = Field(default="info", description="Logging level")


class SyncConfig(BaseModel):
    """Settings that control synchronisation behaviour."""

    interval_minutes: int = Field(default=30, description="Minutes between sync runs")
    mode: Literal["full", "incremental"] = Field(
        default="incremental",
        description="Sync mode",
    )


class SpotifyConfig(BaseModel):
    """Spotify API credentials and OAuth tokens."""

    client_id: str = Field(default="", description="Spotify Developer App client ID")
    client_secret: SecretStr = Field(default=SecretStr(""), description="Spotify Developer App client secret")
    redirect_uri: str = Field(default="http://127.0.0.1:8888/callback", description="OAuth redirect URI")
    refresh_token: SecretStr = Field(default=SecretStr(""), description="Spotify OAuth refresh token")


class YandexConfig(BaseModel):
    """Yandex Music API credentials."""

    token: SecretStr = Field(default=SecretStr(""), description="Yandex Music OAuth token")


class AppConfig(BaseModel):
    """Top-level application configuration."""

    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    spotify: SpotifyConfig = Field(default_factory=SpotifyConfig)
    yandex: YandexConfig = Field(default_factory=YandexConfig)

    # -- derived paths (not stored in TOML) --------------------------------

    @property
    def base_dir(self) -> Path:
        return get_base_dir()

    @property
    def socket_path(self) -> Path:
        return self.base_dir / _SOCKET_FILE

    @property
    def pid_path(self) -> Path:
        return self.base_dir / _PID_FILE

    @property
    def log_dir(self) -> Path:
        return self.base_dir / _LOG_DIR

    def is_spotify_configured(self) -> bool:
        """Return True if Spotify credentials are fully set."""
        return bool(
            self.spotify.client_id
            and self.spotify.client_secret.get_secret_value()
            and self.spotify.refresh_token.get_secret_value()
        )

    def is_yandex_configured(self) -> bool:
        """Return True if the Yandex Music token is set."""
        return bool(self.yandex.token.get_secret_value())


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def ensure_dirs() -> None:
    """Create the base directory and log directory if they don't already exist."""
    base = get_base_dir()
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    (base / _LOG_DIR).mkdir(mode=0o700, parents=True, exist_ok=True)


def config_exists() -> bool:
    """Return True if a config file is present on disk."""
    return (get_base_dir() / _CONFIG_FILE).is_file()


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------


def load_config() -> AppConfig:
    """Load configuration from TOML, falling back to defaults if the file is missing."""
    path = get_base_dir() / _CONFIG_FILE
    if not path.is_file():
        return AppConfig()

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    return AppConfig.model_validate(raw)


def _format_toml_value(value: object) -> str:
    """Format a single Python value as a TOML literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, SecretStr):
        raw = value.get_secret_value()
        escaped = raw.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    msg = f"Unsupported TOML value type: {type(value)}"
    raise TypeError(msg)


def _dump_toml(config: AppConfig) -> str:
    """Serialize an AppConfig to a minimal TOML string.

    Only handles the flat two-level structure we actually use (tables with
    scalar values).  This avoids pulling in a TOML-writing library for now.
    """
    lines: list[str] = []
    sections = [
        ("daemon", config.daemon),
        ("sync", config.sync),
        ("spotify", config.spotify),
        ("yandex", config.yandex),
    ]
    for section_name, section_model in sections:
        lines.append(f"[{section_name}]")
        for key, value in section_model.model_dump(mode="python").items():
            lines.append(f"{key} = {_format_toml_value(value)}")
        lines.append("")  # blank line between sections
    return "\n".join(lines)


def save_config(config: AppConfig) -> None:
    """Save configuration to TOML and restrict file permissions to owner-only."""
    ensure_dirs()
    path = get_base_dir() / _CONFIG_FILE
    path.write_text(_dump_toml(config), encoding="utf-8")
    os.chmod(path, 0o600)
