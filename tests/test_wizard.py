"""Tests for spondex.wizard module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from spondex.wizard import (
    _wizard_spotify,
    _wizard_sync,
    _wizard_yandex,
    run_wizard,
)

# ---------------------------------------------------------------------------
# 1. _wizard_spotify
# ---------------------------------------------------------------------------


def test_wizard_spotify_success():
    """Spotify wizard returns populated SpotifyConfig on successful OAuth."""
    mock_oauth = MagicMock()
    mock_oauth.get_authorize_url.return_value = "https://accounts.spotify.com/authorize?..."
    mock_oauth.get_access_token.return_value = {
        "access_token": "access-abc",
        "refresh_token": "refresh-xyz",
    }

    mock_sp = MagicMock()
    mock_sp.current_user.return_value = {"display_name": "TestUser", "id": "test123"}

    with (
        patch("spondex.wizard.SpotifyOAuth", return_value=mock_oauth),
        patch("spondex.wizard.spotipy.Spotify", return_value=mock_sp),
        patch("rich.prompt.Prompt.ask", side_effect=["my-client-id", "my-secret", "http://127.0.0.1:8888/callback"]),
    ):
        cfg = _wizard_spotify()

    assert cfg.client_id == "my-client-id"
    assert cfg.client_secret.get_secret_value() == "my-secret"
    assert cfg.redirect_uri == "http://127.0.0.1:8888/callback"
    assert cfg.refresh_token.get_secret_value() == "refresh-xyz"


def test_wizard_spotify_no_refresh_token():
    """Returns empty SpotifyConfig when token exchange yields no refresh_token."""
    mock_oauth = MagicMock()
    mock_oauth.get_authorize_url.return_value = "https://example.com"
    mock_oauth.get_access_token.return_value = {"access_token": "only-access"}

    with (
        patch("spondex.wizard.SpotifyOAuth", return_value=mock_oauth),
        patch("rich.prompt.Prompt.ask", side_effect=["id", "secret", "http://127.0.0.1:8888/callback"]),
    ):
        cfg = _wizard_spotify()

    assert cfg.client_id == ""  # empty default


def test_wizard_spotify_none_token_info():
    """Returns empty SpotifyConfig when get_access_token returns None."""
    mock_oauth = MagicMock()
    mock_oauth.get_authorize_url.return_value = "https://example.com"
    mock_oauth.get_access_token.return_value = None

    with (
        patch("spondex.wizard.SpotifyOAuth", return_value=mock_oauth),
        patch("rich.prompt.Prompt.ask", side_effect=["id", "secret", "http://127.0.0.1:8888/callback"]),
    ):
        cfg = _wizard_spotify()

    assert cfg.client_id == ""


# ---------------------------------------------------------------------------
# 2. _wizard_yandex
# ---------------------------------------------------------------------------


def test_wizard_yandex_success():
    """Yandex wizard returns populated YandexConfig on valid token."""
    mock_client = MagicMock()
    mock_client.init.return_value = mock_client
    mock_client.me.account.display_name = "YandexUser"
    mock_client.me.account.login = "user@yandex.ru"

    with (
        patch("spondex.wizard.YandexClient", return_value=mock_client),
        patch("rich.prompt.Prompt.ask", side_effect=["token", "valid-token"]),
    ):
        cfg = _wizard_yandex()

    assert cfg.token.get_secret_value() == "valid-token"


def test_wizard_yandex_invalid_then_skip():
    """Yandex wizard skips when user declines retry after invalid token."""
    mock_client = MagicMock()
    mock_client.init.side_effect = Exception("Unauthorized")

    with (
        patch("spondex.wizard.YandexClient", return_value=mock_client),
        patch("rich.prompt.Prompt.ask", side_effect=["token", "bad-token"]),
        patch("rich.prompt.Confirm.ask", return_value=False),
    ):
        cfg = _wizard_yandex()

    assert cfg.token.get_secret_value() == ""


# ---------------------------------------------------------------------------
# 3. _wizard_sync
# ---------------------------------------------------------------------------


def test_wizard_sync_defaults():
    """Sync wizard returns default values when user accepts them."""
    with patch("rich.prompt.Prompt.ask", side_effect=["incremental", "30"]):
        cfg = _wizard_sync()

    assert cfg.mode == "incremental"
    assert cfg.interval_minutes == 30


def test_wizard_sync_custom_values():
    """Sync wizard returns user-specified values."""
    with patch("rich.prompt.Prompt.ask", side_effect=["full", "10"]):
        cfg = _wizard_sync()

    assert cfg.mode == "full"
    assert cfg.interval_minutes == 10


def test_wizard_sync_invalid_interval_fallback():
    """Sync wizard falls back to 30 for invalid interval."""
    with patch("rich.prompt.Prompt.ask", side_effect=["incremental", "abc"]):
        cfg = _wizard_sync()

    assert cfg.interval_minutes == 30


# ---------------------------------------------------------------------------
# 4. run_wizard (full flow)
# ---------------------------------------------------------------------------


def test_run_wizard_full_flow():
    """Full wizard flow with all external dependencies mocked."""
    mock_oauth = MagicMock()
    mock_oauth.get_authorize_url.return_value = "https://example.com"
    mock_oauth.get_access_token.return_value = {
        "access_token": "sp-access",
        "refresh_token": "sp-refresh",
    }

    mock_sp = MagicMock()
    mock_sp.current_user.return_value = {"display_name": "SpUser"}

    mock_ym = MagicMock()
    mock_ym.init.return_value = mock_ym
    mock_ym.me.account.display_name = "YmUser"
    mock_ym.me.account.login = "ym@ya.ru"

    with (
        patch("spondex.wizard.SpotifyOAuth", return_value=mock_oauth),
        patch("spondex.wizard.spotipy.Spotify", return_value=mock_sp),
        patch("spondex.wizard.YandexClient", return_value=mock_ym),
        patch(
            "rich.prompt.Prompt.ask",
            side_effect=[
                "sp-client-id",  # Spotify client_id
                "sp-client-sec",  # Spotify client_secret
                "http://127.0.0.1:8888/callback",  # Spotify redirect_uri
                "token",  # Yandex auth method
                "ym-token",  # Yandex token
                "full",  # Sync mode
                "15",  # Sync interval
            ],
        ),
    ):
        config = run_wizard()

    assert config.spotify.client_id == "sp-client-id"
    assert config.spotify.client_secret.get_secret_value() == "sp-client-sec"
    assert config.spotify.refresh_token.get_secret_value() == "sp-refresh"
    assert config.yandex.token.get_secret_value() == "ym-token"
    assert config.sync.mode == "full"
    assert config.sync.interval_minutes == 15


def test_wizard_spotify_headless_pasted_url():
    """Headless mode exchanges the code parsed from a pasted redirect URL."""
    mock_oauth = MagicMock()
    mock_oauth.get_authorize_url.return_value = "https://accounts.spotify.com/authorize?..."
    mock_oauth.parse_response_code.side_effect = lambda url: "the-code" if "code=" in url else url
    mock_oauth.get_access_token.return_value = {"access_token": "a", "refresh_token": "r"}

    mock_sp = MagicMock()
    mock_sp.current_user.return_value = {"id": "u"}

    with (
        patch("spondex.wizard.SpotifyOAuth", return_value=mock_oauth) as oauth_cls,
        patch("spondex.wizard.spotipy.Spotify", return_value=mock_sp),
        patch(
            "rich.prompt.Prompt.ask",
            side_effect=[
                "id",
                "secret",
                "http://127.0.0.1:8888/callback",
                "garbage",  # rejected: no code
                "http://127.0.0.1:8888/callback?code=the-code&state=x",
            ],
        ),
    ):
        cfg = _wizard_spotify(headless=True)

    assert oauth_cls.call_args.kwargs["open_browser"] is False
    mock_oauth.get_access_token.assert_called_once_with("the-code", as_dict=True, check_cache=False)
    assert cfg.refresh_token.get_secret_value() == "r"


def test_wizard_yandex_device_login_stores_refresh_token():
    """Device login returns access + refresh token and an expiry."""
    import time

    oauth = MagicMock(access_token="dev-access", refresh_token="dev-refresh", expires_in=31536000)
    code = MagicMock(verification_url="https://ya.ru/device", user_code="ABCD", expires_in=300)

    def device_auth(on_code):
        on_code(code)
        return oauth

    login_client = MagicMock()
    login_client.device_auth.side_effect = device_auth
    check_client = MagicMock()
    check_client.init.return_value = check_client
    check_client.me.account.display_name = "YmUser"

    def make_client(*args):
        return check_client if args else login_client

    with (
        patch("spondex.wizard.YandexClient", side_effect=make_client),
        patch("rich.prompt.Prompt.ask", return_value="device"),
    ):
        cfg = _wizard_yandex()

    assert cfg.token.get_secret_value() == "dev-access"
    assert cfg.refresh_token.get_secret_value() == "dev-refresh"
    assert cfg.expires_at > time.time() + 300 * 24 * 3600
