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
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError
from yandex_music import Client as YandexClient

from spondex.config import AppConfig, SpotifyConfig, SyncConfig, YandexConfig

console = Console()

SPOTIFY_SCOPES = (
    "user-library-read user-library-modify playlist-read-private playlist-modify-private playlist-modify-public"
)


# ---------------------------------------------------------------------------
# Spotify
# ---------------------------------------------------------------------------


def _spotify_token_headless(sp_oauth: SpotifyOAuth) -> dict | None:
    """Run the OAuth code flow without a local browser or callback server.

    The user opens the authorize URL on any machine, gets redirected to the
    (unreachable) redirect URI, and pastes the full redirected URL back here.
    """
    auth_url = sp_oauth.get_authorize_url()
    console.print("\nOpen this URL in a browser on any device and authorize the app:\n")
    # soft_wrap: never insert hard line breaks into the URL, so it stays copyable.
    console.print(auth_url, soft_wrap=True, markup=False, highlight=False)
    console.print(
        "\nThe browser will be redirected to the redirect URI and will probably show\n"
        "an error page — that's expected. Copy the full URL from the address bar\n"
        "(it contains [bold]?code=...[/bold]) and paste it below.\n"
    )
    while True:
        redirected = Prompt.ask("Redirected URL").strip()
        code = sp_oauth.parse_response_code(redirected)
        if code and code != redirected:
            break
        console.print("[yellow]No ?code= parameter found in that URL. Try again.[/yellow]")
    try:
        return sp_oauth.get_access_token(code, as_dict=True, check_cache=False)
    except SpotifyOauthError as exc:
        console.print(f"[red]Spotify rejected the authorization code:[/red] {exc}")
        return None


def _wizard_spotify(headless: bool = False) -> SpotifyConfig:
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
        open_browser=not headless,
    )

    if headless:
        token_info = _spotify_token_headless(sp_oauth)
    else:
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


def _yandex_device_login() -> YandexConfig | None:
    """Log in via OAuth Device Flow; returns config with a refresh token."""
    from spondex.sync.yandex import tokens_from_oauth_response

    def on_code(code) -> None:  # noqa: ANN001
        console.print(
            f"\nOpen [bold]{code.verification_url}[/bold] on any device and enter the code: "
            f"[bold cyan]{code.user_code}[/bold cyan]\n"
            f"Waiting for confirmation (up to {code.expires_in // 60} min)...\n"
        )

    try:
        oauth = YandexClient().device_auth(on_code=on_code)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Yandex login failed:[/red] {exc}")
        return None

    tokens = tokens_from_oauth_response(
        {"access_token": oauth.access_token, "refresh_token": oauth.refresh_token, "expires_in": oauth.expires_in}
    )
    return YandexConfig(
        token=SecretStr(tokens.access_token),
        refresh_token=SecretStr(tokens.refresh_token),
        expires_at=tokens.expires_at,
    )


def _yandex_token_prompt() -> YandexConfig | None:
    token = Prompt.ask("Yandex Music token", password=True).strip()
    if not token:
        console.print("[yellow]Token cannot be empty.[/yellow]")
        return None
    return YandexConfig(token=SecretStr(token))


def _wizard_yandex() -> YandexConfig:
    """Authorize Yandex Music (device login or pasted token) and validate it."""
    console.print("[bold]Step 2: Yandex Music[/bold]")
    console.print(
        "[bold]device[/bold] — log in with a code on the Yandex page; the token is renewed automatically.\n"
        "[bold]token[/bold]  — paste an existing OAuth token (expires in ~1 year, no automatic renewal).\n"
    )

    while True:
        method = Prompt.ask("Authorization method", choices=["device", "token"], default="device")
        cfg = _yandex_device_login() if method == "device" else _yandex_token_prompt()

        if cfg is not None:
            console.print("Validating token...")
            try:
                client = YandexClient(cfg.token.get_secret_value()).init()
                name = client.me.account.display_name or client.me.account.login
                console.print(f"[green]Yandex Music authorized[/green] as [bold]{name}[/bold].\n")
                return cfg
            except Exception:  # noqa: BLE001, S110
                pass

        retry = Confirm.ask("[red]Yandex authorization failed.[/red] Try again?", default=True)
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


def run_wizard(headless: bool = False) -> AppConfig:
    """Run the interactive setup wizard and return a populated AppConfig.

    With *headless* the Spotify step does not open a browser or start a
    local callback server; the user pastes the redirected URL instead.
    """
    console.print("\n[bold cyan]Spondex Setup Wizard[/bold cyan]")
    console.print("Let's configure your music library sync.\n")

    spotify_cfg = _wizard_spotify(headless=headless)
    yandex_cfg = _wizard_yandex()
    sync_cfg = _wizard_sync()

    console.print("[green bold]Configuration complete![/green bold]\n")

    return AppConfig(
        spotify=spotify_cfg,
        yandex=yandex_cfg,
        sync=sync_cfg,
    )
