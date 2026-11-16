"""Tests for the async Yandex Music client wrapper."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from spondex.config import YandexConfig
from spondex.sync.differ import RemoteTrack
from spondex.sync.yandex import YandexClient, YandexTokens


def _make_config() -> YandexConfig:
    return YandexConfig(token=SecretStr("test_token"))


def _make_mock_client() -> MagicMock:
    """Create a mock yandex_music.Client with sensible defaults."""
    mock_client = MagicMock()
    mock_client.init.return_value = mock_client
    return mock_client


def _make_track_short(track_id: str, timestamp: str | None = None) -> MagicMock:
    ts = MagicMock()
    ts.track_id = track_id
    ts.timestamp = timestamp
    return ts


def _make_full_track(track_id: str, title: str, artist_name: str, duration_ms: int | None = None) -> MagicMock:
    track = MagicMock()
    track.id = track_id
    track.title = title
    track.duration_ms = duration_ms
    artist = MagicMock()
    artist.name = artist_name
    track.artists = [artist]
    return track


@pytest.mark.asyncio
async def test_get_liked_tracks() -> None:
    """get_liked_tracks returns correct RemoteTrack list."""
    mock_client = _make_mock_client()

    short1 = _make_track_short("111", "2026-01-10T12:00:00+00:00")
    short2 = _make_track_short("222", "2026-01-20T12:00:00+00:00")
    mock_client.users_likes_tracks.return_value = [short1, short2]

    full1 = _make_full_track("111", "Song One", "Artist A")
    full2 = _make_full_track("222", "Song Two", "Artist B")
    mock_client.tracks.return_value = [full1, full2]

    with patch("yandex_music.Client", return_value=mock_client):
        async with YandexClient(_make_config()) as yc:
            tracks = await yc.get_liked_tracks()

    assert len(tracks) == 2
    assert tracks[0] == RemoteTrack(
        service="yandex",
        remote_id="111",
        artist="Artist A",
        title="Song One",
        added_at="2026-01-10T12:00:00+00:00",
    )
    assert tracks[1] == RemoteTrack(
        service="yandex",
        remote_id="222",
        artist="Artist B",
        title="Song Two",
        added_at="2026-01-20T12:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_get_liked_tracks_since_filters_by_timestamp() -> None:
    """get_liked_tracks with since filters out older tracks."""
    mock_client = _make_mock_client()

    old = _make_track_short("111", "2026-01-05T12:00:00+00:00")
    new = _make_track_short("222", "2026-02-01T12:00:00+00:00")
    mock_client.users_likes_tracks.return_value = [old, new]

    full_new = _make_full_track("222", "New Song", "New Artist")
    mock_client.tracks.return_value = [full_new]

    since = datetime(2026, 1, 15, tzinfo=UTC)

    with patch("yandex_music.Client", return_value=mock_client):
        async with YandexClient(_make_config()) as yc:
            tracks = await yc.get_liked_tracks(since=since)

    assert len(tracks) == 1
    assert tracks[0].remote_id == "222"
    assert tracks[0].title == "New Song"

    # Verify only the new track ID was fetched
    mock_client.tracks.assert_called_once_with(["222"])


@pytest.mark.asyncio
async def test_like_tracks_calls_api() -> None:
    """like_tracks delegates to the client API."""
    mock_client = _make_mock_client()

    with patch("yandex_music.Client", return_value=mock_client):
        async with YandexClient(_make_config()) as yc:
            await yc.like_tracks(["111", "222"])

    mock_client.users_likes_tracks_add.assert_called_once_with(["111", "222"])


@pytest.mark.asyncio
async def test_unlike_tracks_calls_api() -> None:
    """unlike_tracks delegates to the client API."""
    mock_client = _make_mock_client()

    with patch("yandex_music.Client", return_value=mock_client):
        async with YandexClient(_make_config()) as yc:
            await yc.unlike_tracks(["333"])

    mock_client.users_likes_tracks_remove.assert_called_once_with(["333"])


@pytest.mark.asyncio
async def test_search_track_returns_match() -> None:
    """search_track returns a RemoteTrack when a best match is found."""
    mock_client = _make_mock_client()

    best = MagicMock()
    best.type = "track"
    best.result = _make_full_track("999", "Found Song", "Found Artist")

    search_result = MagicMock()
    search_result.best = best
    mock_client.search.return_value = search_result

    with patch("yandex_music.Client", return_value=mock_client):
        async with YandexClient(_make_config()) as yc:
            track = await yc.search_track("Found Artist", "Found Song")

    assert track is not None
    assert track == RemoteTrack(
        service="yandex",
        remote_id="999",
        artist="Found Artist",
        title="Found Song",
    )
    mock_client.search.assert_called_once_with("Found Artist Found Song")


@pytest.mark.asyncio
async def test_search_track_returns_none_when_not_found() -> None:
    """search_track returns None when no best match exists."""
    mock_client = _make_mock_client()

    search_result = MagicMock()
    search_result.best = None
    mock_client.search.return_value = search_result

    with patch("yandex_music.Client", return_value=mock_client):
        async with YandexClient(_make_config()) as yc:
            track = await yc.search_track("Nobody", "No Song")

    assert track is None


# ---------------------------------------------------------------------------
# Auth error contains actionable message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_error_contains_reauth_hint() -> None:
    """YandexAuthError message suggests the re-auth command."""
    from spondex.sync.yandex import YandexAuthError

    with (
        patch("yandex_music.Client", side_effect=Exception("invalid token")),
        pytest.raises(YandexAuthError, match="spondex auth yandex"),
    ):
        async with YandexClient(_make_config()):
            pass


# ---------------------------------------------------------------------------
# Automatic token renewal (device-flow refresh_token)
# ---------------------------------------------------------------------------





def _oauth_transport(calls: list[dict], *, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(httpx.QueryParams(request.content.decode())))
        if status != 200:
            return httpx.Response(status, json={"error": "invalid_grant"})
        return httpx.Response(
            200, json={"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 31536000}
        )

    return httpx.MockTransport(handler)


def _refreshable_config(expires_in: int) -> YandexConfig:
    return YandexConfig(
        token=SecretStr("old-access"),
        refresh_token=SecretStr("old-refresh"),
        expires_at=int(time.time()) + expires_in,
    )


@pytest.mark.asyncio
async def test_token_renewed_when_expiring_soon() -> None:
    calls: list[dict] = []
    saved: list[YandexTokens] = []
    config = _refreshable_config(expires_in=3 * 24 * 3600)

    with patch("yandex_music.Client", return_value=_make_mock_client()) as client_cls:
        async with YandexClient(config, on_tokens_updated=saved.append, _oauth_transport=_oauth_transport(calls)):
            pass

    assert calls[0]["grant_type"] == "refresh_token"
    assert calls[0]["refresh_token"] == "old-refresh"
    assert client_cls.call_args.args[0] == "new-access"
    assert config.token.get_secret_value() == "new-access"
    assert config.refresh_token.get_secret_value() == "new-refresh"
    assert config.expires_at > time.time() + 300 * 24 * 3600
    assert saved and saved[0].access_token == "new-access"


@pytest.mark.asyncio
async def test_token_not_renewed_when_fresh() -> None:
    calls: list[dict] = []
    config = _refreshable_config(expires_in=200 * 24 * 3600)

    with patch("yandex_music.Client", return_value=_make_mock_client()):
        async with YandexClient(config, on_tokens_updated=lambda t: None, _oauth_transport=_oauth_transport(calls)):
            pass

    assert calls == []
    assert config.token.get_secret_value() == "old-access"


@pytest.mark.asyncio
async def test_no_refresh_token_means_no_renewal() -> None:
    calls: list[dict] = []
    with patch("yandex_music.Client", return_value=_make_mock_client()):
        async with YandexClient(_make_config(), _oauth_transport=_oauth_transport(calls)):
            pass
    assert calls == []


@pytest.mark.asyncio
async def test_rejected_token_is_renewed_and_retried() -> None:
    calls: list[dict] = []
    config = _refreshable_config(expires_in=200 * 24 * 3600)
    good = _make_mock_client()

    def make_client(token):
        if token == "old-access":
            raise Exception("401 Unauthorized")
        return good

    with patch("yandex_music.Client", side_effect=make_client):
        transport = _oauth_transport(calls)
        async with YandexClient(config, on_tokens_updated=lambda t: None, _oauth_transport=transport) as yc:
            assert yc._client is good

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_failed_renewal_falls_back_to_current_token() -> None:
    calls: list[dict] = []
    config = _refreshable_config(expires_in=3 * 24 * 3600)

    with patch("yandex_music.Client", return_value=_make_mock_client()) as client_cls:
        async with YandexClient(
            config, on_tokens_updated=lambda t: None, _oauth_transport=_oauth_transport(calls, status=400)
        ):
            pass

    assert client_cls.call_args.args[0] == "old-access"
