"""Tests for the async Yandex Music client wrapper."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from spondex.config import YandexConfig
from spondex.sync.differ import RemoteTrack
from spondex.sync.yandex import YandexClient


def _make_config() -> YandexConfig:
    return YandexConfig(token=SecretStr("test_token"))


def _make_mock_client() -> MagicMock:
    """Create a mock yandex_music.Client with sensible defaults."""
    mock_client = MagicMock()
    mock_client.init.return_value = mock_client
    return mock_client


def _make_track_short(
    track_id: str, timestamp: str | None = None
) -> MagicMock:
    ts = MagicMock()
    ts.track_id = track_id
    ts.timestamp = timestamp
    return ts


def _make_full_track(
    track_id: str, title: str, artist_name: str, duration_ms: int | None = None
) -> MagicMock:
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

    since = datetime(2026, 1, 15, tzinfo=timezone.utc)

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
