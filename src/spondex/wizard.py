"""Interactive setup wizard for Spondex.

Guides the user through:
  1. Spotify OAuth 2.0 Authorization Code flow (via spotipy)
  2. Yandex Music token input and validation (via yandex-music)
  3. Sync mode and interval selection
"""

from __future__ import annotations

import spotipy
from pydantic import SecretStr
from rich.console import Console
from rich.prompt import Confirm, Prompt
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyOAuth
from yandex_music import Client as YandexClient

from spondex.config import AppConfig, SpotifyConfig, SyncConfig, YandexConfig

console = Console()

SPOTIFY_SCOPES = (
    "user-library-read user-library-modify playlist-read-private playlist-modify-private playlist-modify-public"
)


# ---------------------------------------------------------------------------
# Spotify
# ---------------------------------------------------------------------------


def _wizard_spotify() -> SpotifyConfig:
    """Walk the user through Spotify OAuth and return populated config."""
    console.print("[bold]Step 1: Spotify[/bold]")
    console.print(
        "Create a Spotify Developer app at "
        "[link]https://developer.spotify.com/dashboard[/link]\n"
        "Set a redirect URI (e.g. [bold]http://127.0.0.1:8888/callback[/bold])\n"
    )

    client_id = Prompt.ask("Spotify Client ID").strip()
    client_secret = Prompt.ask("Spotify Client Secret", password=True).strip()
    redirect_uri = Prompt.ask(
        "Redirect URI",
        default="http://127.0.0.1:8888/callback",
    ).strip()

    # Use MemoryCacheHandler so spotipy doesn't create .cache files.
    sp_oauth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SPOTIFY_SCOPES,
        cache_handler=MemoryCacheHandler(),
        open_browser=True,
    )

    console.print("\nOpening browser for Spotify authorization...")
    auth_url = sp_oauth.get_authorize_url()
    console.print(f"If the browser does not open, visit:\n  [link]{auth_url}[/link]\n")

    # get_access_token() handles the full flow: opens browser, starts local
    # callback server, waits for the redirect, exchanges the code for tokens.
    token_info = sp_oauth.get_access_token(as_dict=True)

    if not token_info or "refresh_token" not in token_info:
        console.print("[red]Failed to obtain Spotify tokens.[/red]")
        return SpotifyConfig()

    # Verify the token works by fetching the current user profile.
    sp = spotipy.Spotify(auth=token_info["access_token"])
    user = sp.current_user()
    console.print(
        "[green]Spotify authorized[/green] as [bold]{name}[/bold].\n".format(
            name=user.get("display_name", user.get("id", "?"))
        )
    )

    return SpotifyConfig(
        client_id=client_id,
        client_secret=SecretStr(client_secret),
        redirect_uri=redirect_uri,
        refresh_token=SecretStr(token_info["refresh_token"]),
    )


# ---------------------------------------------------------------------------
# Yandex Music
# ---------------------------------------------------------------------------


def _wizard_yandex() -> YandexConfig:
    """Prompt for a Yandex Music token and validate it."""
    console.print("[bold]Step 2: Yandex Music[/bold]")
    console.print(
        "Enter your Yandex Music OAuth token.\nYou can obtain it using browser dev-tools or a dedicated helper.\n"
    )

    while True:
        token = Prompt.ask("Yandex Music token", password=True).strip()

        if not token:
            console.print("[yellow]Token cannot be empty. Try again.[/yellow]")
            continue

        console.print("Validating token...")
        try:
            client = YandexClient(token).init()
            name = client.me.account.display_name or client.me.account.login
            console.print(f"[green]Yandex Music authorized[/green] as [bold]{name}[/bold].\n")
            return YandexConfig(token=SecretStr(token))
        except Exception:  # noqa: BLE001
            retry = Confirm.ask(
                "[red]Token validation failed.[/red] Try again?",
                default=True,
            )
            if not retry:
                console.print("[yellow]Skipping Yandex Music setup.[/yellow]\n")
                return YandexConfig()


# ---------------------------------------------------------------------------
# Sync settings
# ---------------------------------------------------------------------------


def _wizard_sync() -> SyncConfig:
    """Let the user pick sync mode and interval."""
    console.print("[bold]Step 3: Sync settings[/bold]")

    mode = Prompt.ask(
        "Sync mode",
        choices=["full", "incremental"],
        default="incremental",
    )

    interval_str = Prompt.ask("Sync interval in minutes", default="30")
    try:
        interval = int(interval_str)
        if interval < 1:
            raise ValueError
    except ValueError:
        console.print("[yellow]Invalid interval, using default 30 minutes.[/yellow]")
        interval = 30

    console.print()
    return SyncConfig(mode=mode, interval_minutes=interval)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_wizard() -> AppConfig:
    """Run the interactive setup wizard and return a populated AppConfig."""
    console.print("\n[bold cyan]Spondex Setup Wizard[/bold cyan]")
    console.print("Let's configure your music library sync.\n")

    spotify_cfg = _wizard_spotify()
    yandex_cfg = _wizard_yandex()
    sync_cfg = _wizard_sync()

    console.print("[green bold]Configuration complete![/green bold]\n")

    return AppConfig(
        spotify=spotify_cfg,
        yandex=yandex_cfg,
        sync=sync_cfg,
    )
