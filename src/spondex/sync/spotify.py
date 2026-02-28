"""Async Spotify Web API client using httpx.

Endpoints:
- GET /me/tracks (listing liked tracks)
- PUT /me/tracks (save tracks, body: {"ids": [...]})
- DELETE /me/tracks (remove tracks, body: {"ids": [...]})
- GET /search (limit max 10)
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

import httpx
import structlog

from spondex.config import SpotifyConfig
from spondex.sync.differ import RemoteTrack

log = structlog.get_logger(__name__)

_API_BASE = "https://api.spotify.com/v1"
_TOKEN_URL = "https://accounts.spotify.com/api/token"  # noqa: S105
_BATCH_SIZE = 50
_SEARCH_LIMIT = 10
_MAX_RETRIES = 3


class SpotifyAuthError(Exception):
    """Raised when Spotify authentication fails."""


class SpotifyAPIError(Exception):
    """Raised for non-retryable Spotify API errors."""


class SpotifyClient:
    """Async Spotify Web API client with automatic token refresh."""

    def __init__(
        self,
        config: SpotifyConfig,
        *,
        _transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = _transport
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> SpotifyClient:
        kw: dict = {"timeout": 30.0}
        if self._transport is not None:
            kw["transport"] = self._transport
        self._client = httpx.AsyncClient(**kw)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # -- auth --

    async def _ensure_token(self, *, force: bool = False) -> str:
        if not force and self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        assert self._client is not None  # noqa: S101
        resp = await self._client.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._config.refresh_token.get_secret_value(),
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret.get_secret_value(),
            },
        )
        if resp.status_code != 200:
            raise SpotifyAuthError(f"Token refresh failed: {resp.status_code} {resp.text}")

        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)
        return self._access_token

    # -- request helper --

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict | list | None = None,
        params: dict | None = None,
    ) -> httpx.Response:
        assert self._client is not None  # noqa: S101

        for attempt in range(_MAX_RETRIES):
            token = await self._ensure_token()
            headers = {"Authorization": f"Bearer {token}"}

            try:
                resp = await self._client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                )
            except httpx.TransportError as exc:
                if attempt >= _MAX_RETRIES - 1:
                    raise SpotifyAPIError(f"Network error after {_MAX_RETRIES} retries: {exc}") from exc
                wait = 2**attempt
                log.warning(
                    "spotify_network_error",
                    error=str(exc),
                    retry_in=wait,
                    attempt=attempt,
                )
                await asyncio.sleep(wait)
                continue

            if resp.status_code == 401 and attempt == 0:
                # Token expired mid-request, force refresh
                await self._ensure_token(force=True)
                continue

            if resp.status_code == 401 and attempt > 0:
                raise SpotifyAuthError(
                    "Spotify authentication failed after token refresh. "
                    "Your refresh_token may be invalid — run: "
                    "spondex config set spotify.refresh_token <new_token>"
                )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "1"))
                log.warning(
                    "spotify_rate_limited",
                    retry_after=retry_after,
                    attempt=attempt,
                )
                await asyncio.sleep(retry_after)
                continue

            if resp.status_code >= 400:
                raise SpotifyAPIError(f"Spotify API error: {resp.status_code} {resp.text}")

            return resp

        raise SpotifyAPIError(f"Max retries ({_MAX_RETRIES}) exceeded")

    # -- public API --

    async def get_liked_tracks(
        self,
        *,
        since: datetime | None = None,
    ) -> list[RemoteTrack]:
        """Fetch liked tracks from Spotify.

        Args:
            since: If provided (incremental mode), stop paginating when
                   ``added_at < since``.  Spotify returns newest first.

        Returns:
            List of :class:`RemoteTrack` with ``service="spotify"``.
        """
        tracks: list[RemoteTrack] = []
        offset = 0

        while True:
            resp = await self._request(
                "GET",
                f"{_API_BASE}/me/tracks",
                params={"limit": 50, "offset": offset},
            )
            data = resp.json()

            page_items = data.get("items", [])
            if not page_items:
                break

            stop_paging = False
            for item in page_items:
                track = item["track"]
                added_at_str = item.get("added_at")

                # Incremental: check timestamp
                if since and added_at_str:
                    added_dt = datetime.fromisoformat(added_at_str.replace("Z", "+00:00"))
                    if added_dt < since:
                        stop_paging = True
                        break

                artists = track.get("artists", [])
                artist_name = artists[0]["name"] if artists else "Unknown"

                tracks.append(
                    RemoteTrack(
                        service="spotify",
                        remote_id=track["id"],
                        artist=artist_name,
                        title=track["name"],
                        added_at=added_at_str,
                        duration_ms=track.get("duration_ms"),
                    )
                )

            if stop_paging or data.get("next") is None:
                break

            offset += 50

        return tracks

    async def save_tracks(self, track_ids: list[str]) -> None:
        """Save tracks to the user's library in batches of 50."""
        for i in range(0, len(track_ids), _BATCH_SIZE):
            batch = track_ids[i : i + _BATCH_SIZE]
            await self._request("PUT", f"{_API_BASE}/me/tracks", json={"ids": batch})

    async def remove_tracks(self, track_ids: list[str]) -> None:
        """Remove tracks from the user's library in batches of 50."""
        for i in range(0, len(track_ids), _BATCH_SIZE):
            batch = track_ids[i : i + _BATCH_SIZE]
            await self._request("DELETE", f"{_API_BASE}/me/tracks", json={"ids": batch})

    async def search_track(self, artist: str, title: str) -> RemoteTrack | None:
        """Search for a track on Spotify by artist and title.

        Returns the best match as a :class:`RemoteTrack`, or ``None`` if
        no results were found.
        """
        query = f"{artist} {title}"
        resp = await self._request(
            "GET",
            f"{_API_BASE}/search",
            params={"q": query, "type": "track", "limit": _SEARCH_LIMIT},
        )
        data = resp.json()
        items = data.get("tracks", {}).get("items", [])
        if not items:
            return None

        best = items[0]
        artists = best.get("artists", [])
        artist_name = artists[0]["name"] if artists else "Unknown"

        return RemoteTrack(
            service="spotify",
            remote_id=best["id"],
            artist=artist_name,
            title=best["name"],
            duration_ms=best.get("duration_ms"),
        )
