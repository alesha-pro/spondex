"""Async wrapper around the yandex-music library.

The yandex-music library is synchronous; all calls are wrapped in
asyncio.to_thread() to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import structlog

from spondex.config import YandexConfig
from spondex.sync.differ import RemoteTrack

log = structlog.get_logger(__name__)

_BATCH_SIZE = 100


class YandexAuthError(Exception):
    """Raised when Yandex Music authentication fails."""


class YandexAPIError(Exception):
    """Raised for Yandex Music API errors."""


class YandexClient:
    """Async wrapper around the synchronous yandex-music library."""

    def __init__(self, config: YandexConfig) -> None:
        self._config = config
        self._client = None  # yandex_music.Client, set in __aenter__

    async def __aenter__(self) -> YandexClient:
        from yandex_music import Client

        token = self._config.token.get_secret_value()
        try:
            client = await asyncio.to_thread(Client, token)
            self._client = await asyncio.to_thread(client.init)
        except Exception as exc:
            raise YandexAuthError(f"Yandex Music auth failed: {exc}") from exc
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._client = None

    async def get_liked_tracks(
        self, *, since: datetime | None = None
    ) -> list[RemoteTrack]:
        """Fetch liked tracks, optionally filtered by timestamp."""
        assert self._client is not None

        # Step 1: Get all liked track short infos
        likes = await asyncio.to_thread(self._client.users_likes_tracks)

        if not likes:
            return []

        # The likes object may be a TracksList or list
        track_shorts = (
            likes if isinstance(likes, list) else getattr(likes, "tracks", likes)
        )

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
            await asyncio.to_thread(
                self._client.users_likes_tracks_add, track_ids
            )

    async def unlike_tracks(self, track_ids: list[str]) -> None:
        """Remove tracks from liked."""
        assert self._client is not None
        if track_ids:
            await asyncio.to_thread(
                self._client.users_likes_tracks_remove, track_ids
            )

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
