"""Tests for SpotifyClient using httpx.MockTransport."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from spondex.config import SpotifyConfig
from spondex.sync.spotify import SpotifyClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> SpotifyConfig:
    return SpotifyConfig(
        client_id="test-client-id",
        client_secret="test-client-secret",
        redirect_uri="http://127.0.0.1:8888/callback",
        refresh_token="test-refresh-token",
    )


def _token_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": "mock-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "user-library-read user-library-modify",
        },
    )


def _liked_tracks_page(items: list[dict], *, has_next: bool = False) -> dict:
    return {
        "items": items,
        "next": "http://next" if has_next else None,
        "total": len(items),
    }


def _make_track_item(
    track_id: str,
    artist: str,
    title: str,
    added_at: str = "2026-02-15T10:00:00Z",
) -> dict:
    return {
        "added_at": added_at,
        "track": {
            "id": track_id,
            "name": title,
            "artists": [{"name": artist}],
        },
    }


def _search_response(items: list[dict]) -> dict:
    return {"tracks": {"items": items}}


def _search_track_item(track_id: str, artist: str, title: str) -> dict:
    return {
        "id": track_id,
        "name": title,
        "artists": [{"name": artist}],
    }


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_refresh() -> None:
    """Successful token refresh stores the access token."""
    call_log: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com":
            call_log.append("token")
            return _token_response()
        if str(request.url).startswith("https://api.spotify.com/v1/me/tracks"):
            return httpx.Response(200, json=_liked_tracks_page([]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    config = _make_config()

    async with SpotifyClient(config, _transport=transport) as client:
        await client.get_liked_tracks()

    assert "token" in call_log


# ---------------------------------------------------------------------------
# get_liked_tracks pagination (2 pages)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_liked_tracks_pagination() -> None:
    """Two pages of liked tracks are fetched correctly."""
    page1_items = [
        _make_track_item("t1", "Artist A", "Song One", "2026-02-20T12:00:00Z"),
        _make_track_item("t2", "Artist B", "Song Two", "2026-02-19T12:00:00Z"),
    ]
    page2_items = [
        _make_track_item("t3", "Artist C", "Song Three", "2026-02-18T12:00:00Z"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com":
            return _token_response()
        if str(request.url).startswith("https://api.spotify.com/v1/me/tracks"):
            offset = int(request.url.params.get("offset", "0"))
            if offset == 0:
                return httpx.Response(200, json=_liked_tracks_page(page1_items, has_next=True))
            return httpx.Response(200, json=_liked_tracks_page(page2_items, has_next=False))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    config = _make_config()

    async with SpotifyClient(config, _transport=transport) as client:
        tracks = await client.get_liked_tracks()

    assert len(tracks) == 3
    assert tracks[0].remote_id == "t1"
    assert tracks[1].remote_id == "t2"
    assert tracks[2].remote_id == "t3"
    assert all(t.service == "spotify" for t in tracks)


# ---------------------------------------------------------------------------
# get_liked_tracks with since (early stop)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_liked_tracks_since_early_stop() -> None:
    """Pagination stops when added_at < since."""
    items = [
        _make_track_item("t1", "Artist A", "New Song", "2026-02-25T12:00:00Z"),
        _make_track_item("t2", "Artist B", "Old Song", "2026-02-10T12:00:00Z"),
        _make_track_item("t3", "Artist C", "Older Song", "2026-02-05T12:00:00Z"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com":
            return _token_response()
        if str(request.url).startswith("https://api.spotify.com/v1/me/tracks"):
            return httpx.Response(200, json=_liked_tracks_page(items, has_next=True))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    config = _make_config()

    since = datetime(2026, 2, 15, tzinfo=UTC)

    async with SpotifyClient(config, _transport=transport) as client:
        tracks = await client.get_liked_tracks(since=since)

    # Only t1 should be returned (t2 is before since cutoff)
    assert len(tracks) == 1
    assert tracks[0].remote_id == "t1"


# ---------------------------------------------------------------------------
# save_tracks batching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_tracks_batching() -> None:
    """save_tracks splits into batches of 50."""
    put_bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com":
            return _token_response()
        if request.method == "PUT" and str(request.url).startswith("https://api.spotify.com/v1/me/tracks"):
            put_bodies.append(json.loads(request.content))
            return httpx.Response(200)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    config = _make_config()

    track_ids = [f"id{i}" for i in range(75)]

    async with SpotifyClient(config, _transport=transport) as client:
        await client.save_tracks(track_ids)

    assert len(put_bodies) == 2
    assert len(put_bodies[0]["ids"]) == 50
    assert len(put_bodies[1]["ids"]) == 25
    assert put_bodies[0]["ids"][0] == "id0"
    assert put_bodies[1]["ids"][-1] == "id74"


# ---------------------------------------------------------------------------
# remove_tracks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_tracks() -> None:
    """remove_tracks sends DELETE with correct URIs."""
    delete_bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com":
            return _token_response()
        if request.method == "DELETE" and str(request.url).startswith("https://api.spotify.com/v1/me/tracks"):
            delete_bodies.append(json.loads(request.content))
            return httpx.Response(200)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    config = _make_config()

    async with SpotifyClient(config, _transport=transport) as client:
        await client.remove_tracks(["abc", "def", "ghi"])

    assert len(delete_bodies) == 1
    assert delete_bodies[0]["ids"] == ["abc", "def", "ghi"]


# ---------------------------------------------------------------------------
# search_track found / not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_track_found() -> None:
    """search_track returns best match as RemoteTrack."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com":
            return _token_response()
        if str(request.url).startswith("https://api.spotify.com/v1/search"):
            items = [_search_track_item("found1", "Daft Punk", "Get Lucky")]
            return httpx.Response(200, json=_search_response(items))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    config = _make_config()

    async with SpotifyClient(config, _transport=transport) as client:
        result = await client.search_track("Daft Punk", "Get Lucky")

    assert result is not None
    assert result.remote_id == "found1"
    assert result.artist == "Daft Punk"
    assert result.title == "Get Lucky"
    assert result.service == "spotify"


@pytest.mark.asyncio
async def test_search_track_not_found() -> None:
    """search_track returns None when no results."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com":
            return _token_response()
        if str(request.url).startswith("https://api.spotify.com/v1/search"):
            return httpx.Response(200, json=_search_response([]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    config = _make_config()

    async with SpotifyClient(config, _transport=transport) as client:
        result = await client.search_track("Nonexistent", "Track")

    assert result is None


# ---------------------------------------------------------------------------
# 429 rate limit retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client retries on 429 with Retry-After header."""
    # Patch asyncio.sleep to avoid real waiting
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("spondex.sync.spotify.asyncio.sleep", fake_sleep)

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if request.url.host == "accounts.spotify.com":
            return _token_response()
        if str(request.url).startswith("https://api.spotify.com/v1/me/tracks"):
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, headers={"Retry-After": "2"}, json={"error": "rate limited"})
            return httpx.Response(200, json=_liked_tracks_page([]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    config = _make_config()

    async with SpotifyClient(config, _transport=transport) as client:
        tracks = await client.get_liked_tracks()

    assert tracks == []
    assert call_count == 2
    assert sleep_calls == [2.0]


# ---------------------------------------------------------------------------
# 401 token refresh retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_token_refresh_retry() -> None:
    """Client refreshes token and retries on 401."""
    token_refresh_count = 0
    api_call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_refresh_count, api_call_count
        if request.url.host == "accounts.spotify.com":
            token_refresh_count += 1
            return _token_response()
        if str(request.url).startswith("https://api.spotify.com/v1/me/tracks"):
            api_call_count += 1
            if api_call_count == 1:
                return httpx.Response(401, json={"error": "token expired"})
            return httpx.Response(200, json=_liked_tracks_page([]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    config = _make_config()

    async with SpotifyClient(config, _transport=transport) as client:
        tracks = await client.get_liked_tracks()

    assert tracks == []
    assert api_call_count == 2
    # Initial token fetch + force refresh after 401
    assert token_refresh_count == 2


# ---------------------------------------------------------------------------
# 401 double-fail (actionable error message)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_double_fail_actionable_message() -> None:
    """Repeated 401 raises SpotifyAuthError with actionable message."""
    from spondex.sync.spotify import SpotifyAuthError

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com":
            return _token_response()
        if str(request.url).startswith("https://api.spotify.com/v1/me/tracks"):
            return httpx.Response(401, json={"error": "invalid token"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    config = _make_config()

    async with SpotifyClient(config, _transport=transport) as client:
        with pytest.raises(SpotifyAuthError, match="config set"):
            await client.get_liked_tracks()


# ---------------------------------------------------------------------------
# Network retry with exponential backoff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_retry_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client retries on network error and succeeds."""
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("spondex.sync.spotify.asyncio.sleep", fake_sleep)

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if request.url.host == "accounts.spotify.com":
            return _token_response()
        if str(request.url).startswith("https://api.spotify.com/v1/me/tracks"):
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(200, json=_liked_tracks_page([]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    config = _make_config()

    async with SpotifyClient(config, _transport=transport) as client:
        tracks = await client.get_liked_tracks()

    assert tracks == []
    assert call_count == 2
    assert sleep_calls == [1.0]  # 2^0 = 1


@pytest.mark.asyncio
async def test_network_retry_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client raises after exhausting network retries."""
    from spondex.sync.spotify import SpotifyAPIError

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("spondex.sync.spotify.asyncio.sleep", fake_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com":
            return _token_response()
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(handler)
    config = _make_config()

    async with SpotifyClient(config, _transport=transport) as client:
        with pytest.raises(SpotifyAPIError, match="Network error"):
            await client.get_liked_tracks()
