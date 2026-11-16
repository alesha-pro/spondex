"""Async wrapper around the yandex-music library.

The yandex-music library is synchronous; all calls are wrapped in
asyncio.to_thread() to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx
import structlog
from pydantic import SecretStr

from spondex.config import YandexConfig
from spondex.sync.differ import RemoteTrack

log = structlog.get_logger(__name__)

_BATCH_SIZE = 100

# Renew the OAuth token when it has less than this left (tokens live ~1 year).
_REFRESH_BEFORE_SECONDS = 30 * 24 * 3600

_AUTH_HINT = "Re-authorize with: spondex auth yandex"


class YandexAuthError(Exception):
    """Raised when Yandex Music authentication fails."""


class YandexAPIError(Exception):
    """Raised for Yandex Music API errors."""


@dataclass(frozen=True)
class YandexTokens:
    """OAuth token set returned by the Yandex OAuth server."""

    access_token: str
    refresh_token: str
    expires_at: int  # unix time, 0 = unknown


def _oauth_client_credentials() -> tuple[str, str, str]:
    """OAuth endpoint and the Yandex Music app credentials bundled with yandex-music."""
    from yandex_music._client import device_auth

    return device_auth._OAUTH_BASE_URL, device_auth._DEFAULT_CLIENT_ID, device_auth._DEFAULT_CLIENT_SECRET


def tokens_from_oauth_response(data: dict, *, previous_refresh_token: str = "") -> YandexTokens:
    expires_in = int(data.get("expires_in") or 0)
    return YandexTokens(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token") or previous_refresh_token,
        expires_at=int(time.time()) + expires_in if expires_in else 0,
    )


async def refresh_yandex_tokens(
    refresh_token: str,
    *,
    _transport: httpx.AsyncBaseTransport | None = None,
) -> YandexTokens:
    """Exchange a refresh token for a new access token (``grant_type=refresh_token``)."""
    base_url, client_id, client_secret = _oauth_client_credentials()
    kw: dict = {"timeout": 30.0}
    if _transport is not None:
        kw["transport"] = _transport
    async with httpx.AsyncClient(**kw) as http:
        resp = await http.post(
            f"{base_url}/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
    if resp.status_code != 200:
        raise YandexAuthError(f"Yandex token refresh failed: {resp.status_code} {resp.text}. {_AUTH_HINT}")
    return tokens_from_oauth_response(resp.json(), previous_refresh_token=refresh_token)


def _persist_tokens(tokens: YandexTokens) -> None:
    from spondex.config import persist_fields

    persist_fields(
        "yandex",
        token=SecretStr(tokens.access_token),
        refresh_token=SecretStr(tokens.refresh_token),
        expires_at=tokens.expires_at,
    )


class YandexClient:
    """Async wrapper around the synchronous yandex-music library.

    If the config holds a ``refresh_token`` (device-flow login), the access
    token is renewed automatically when it is close to expiry or rejected,
    and the new tokens are written back to ``config.toml``.
    """

    def __init__(
        self,
        config: YandexConfig,
        *,
        on_tokens_updated: Callable[[YandexTokens], None] | None = None,
        _oauth_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._client = None  # yandex_music.Client, set in __aenter__
        self._on_tokens_updated = on_tokens_updated if on_tokens_updated is not None else _persist_tokens
        self._oauth_transport = _oauth_transport

    # -- auth --

    def _can_refresh(self) -> bool:
        return bool(self._config.refresh_token.get_secret_value())

    def _expiring_soon(self) -> bool:
        expires_at = self._config.expires_at
        # Unknown expiry with a refresh token: renew once to learn it.
        return expires_at == 0 or expires_at - time.time() < _REFRESH_BEFORE_SECONDS

    async def _refresh(self, reason: str) -> None:
        tokens = await refresh_yandex_tokens(
            self._config.refresh_token.get_secret_value(),
            _transport=self._oauth_transport,
        )
        self._config.token = SecretStr(tokens.access_token)
        self._config.refresh_token = SecretStr(tokens.refresh_token)
        self._config.expires_at = tokens.expires_at
        try:
            self._on_tokens_updated(tokens)
        except Exception:
            log.exception("failed to persist renewed yandex token")
        log.info("yandex token renewed", reason=reason, expires_at=tokens.expires_at)

    async def _init_client(self):
        from yandex_music import Client

        client = await asyncio.to_thread(Client, self._config.token.get_secret_value())
        return await asyncio.to_thread(client.init)

    async def __aenter__(self) -> YandexClient:
        refreshed = False
        if self._can_refresh() and self._expiring_soon():
            try:
                await self._refresh(reason="expiring")
                refreshed = True
            except Exception as exc:  # current token may still be valid — keep going
                log.warning("yandex token renewal failed", error=str(exc))

        try:
            self._client = await self._init_client()
        except Exception as exc:
            if not self._can_refresh() or refreshed:
                raise YandexAuthError(f"Yandex Music auth failed: {exc}. {_AUTH_HINT}") from exc
            # Token rejected — try once more with a renewed one.
            await self._refresh(reason="rejected")
            try:
                self._client = await self._init_client()
            except Exception as exc2:
                raise YandexAuthError(f"Yandex Music auth failed: {exc2}. {_AUTH_HINT}") from exc2
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._client = None

    async def get_liked_tracks(self, *, since: datetime | None = None) -> list[RemoteTrack]:
        """Fetch liked tracks, optionally filtered by timestamp."""
        assert self._client is not None

        # Step 1: Get all liked track short infos
        likes = await asyncio.to_thread(self._client.users_likes_tracks)

        if not likes:
            return []

        # The likes object may be a TracksList or list
        track_shorts = likes if isinstance(likes, list) else getattr(likes, "tracks", likes)

        if not track_shorts:
            return []

        # Build timestamp lookup and filter if incremental
        timestamps: dict[str, str | None] = {}
        track_ids: list[str] = []

        for ts in track_shorts:
            tid = str(ts.track_id) if hasattr(ts, "track_id") else str(ts.id)
            # Handle trackId:albumId format
            if ":" in tid:
                tid = tid.split(":")[0]

            ts_str = getattr(ts, "timestamp", None)

            # Incremental filter
            if since and ts_str:
                try:
                    ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts_dt < since:
                        continue
                except (ValueError, AttributeError):
                    pass

            track_ids.append(tid)
            timestamps[tid] = ts_str

        if not track_ids:
            return []

        # Step 2: Batch fetch full track objects
        all_tracks = []
        for i in range(0, len(track_ids), _BATCH_SIZE):
            batch = track_ids[i : i + _BATCH_SIZE]
            full_tracks = await asyncio.to_thread(self._client.tracks, batch)
            if full_tracks:
                all_tracks.extend(full_tracks)

        # Step 3: Build RemoteTrack list
        result: list[RemoteTrack] = []
        for ft in all_tracks:
            tid = str(ft.id)
            artists = getattr(ft, "artists", None)
            artist_name = artists[0].name if artists else "Unknown"
            title = ft.title or "Unknown"

            duration = getattr(ft, "duration_ms", None)

            result.append(
                RemoteTrack(
                    service="yandex",
                    remote_id=tid,
                    artist=artist_name,
                    title=title,
                    added_at=timestamps.get(tid),
                    duration_ms=duration,
                )
            )

        return result

    async def like_tracks(self, track_ids: list[str]) -> None:
        """Add tracks to liked."""
        assert self._client is not None
        if track_ids:
            await asyncio.to_thread(self._client.users_likes_tracks_add, track_ids)

    async def unlike_tracks(self, track_ids: list[str]) -> None:
        """Remove tracks from liked."""
        assert self._client is not None
        if track_ids:
            await asyncio.to_thread(self._client.users_likes_tracks_remove, track_ids)

    async def search_track(self, artist: str, title: str) -> RemoteTrack | None:
        """Search for a track on Yandex Music."""
        assert self._client is not None

        query = f"{artist} {title}"
        result = await asyncio.to_thread(self._client.search, query)

        if result and result.best and result.best.type == "track":
            track = result.best.result
            artists = getattr(track, "artists", None)
            artist_name = artists[0].name if artists else "Unknown"
            duration = getattr(track, "duration_ms", None)
            return RemoteTrack(
                service="yandex",
                remote_id=str(track.id),
                artist=artist_name,
                title=track.title,
                duration_ms=duration,
            )

        return None
