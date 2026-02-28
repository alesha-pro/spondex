"""Core sync engine for bidirectional Spotify ↔ Yandex Music synchronization."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

import structlog

from spondex.sync.differ import cross_match, normalize, transliterate

if TYPE_CHECKING:
    from spondex.config import AppConfig
    from spondex.storage.database import Database
    from spondex.storage.models import SyncMode
    from spondex.sync.spotify import SpotifyClient
    from spondex.sync.yandex import YandexClient

log = structlog.get_logger(__name__)

_MAX_UNMATCHED_ATTEMPTS = 5


class SyncState(StrEnum):
    IDLE = "idle"
    SYNCING = "syncing"
    PAUSED = "paused"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"


@dataclass
class SyncStats:
    sp_added: int = 0
    ym_added: int = 0
    sp_removed: int = 0
    ym_removed: int = 0
    cross_matched: int = 0
    unmatched: int = 0
    retried_ok: int = 0
    errors: int = 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "sp_added": self.sp_added,
                "ym_added": self.ym_added,
                "sp_removed": self.sp_removed,
                "ym_removed": self.ym_removed,
                "cross_matched": self.cross_matched,
                "unmatched": self.unmatched,
                "retried_ok": self.retried_ok,
                "errors": self.errors,
            }
        )


class SyncEngine:
    """Orchestrates bidirectional sync between Spotify and Yandex Music."""

    def __init__(
        self,
        config: AppConfig,
        db: Database,
        *,
        sp_factory: type[SpotifyClient] | None = None,
        ym_factory: type[YandexClient] | None = None,
    ) -> None:
        self._config = config
        self._db = db
        self._sp_factory = sp_factory
        self._ym_factory = ym_factory
        self._state = SyncState.IDLE
        self._lock = asyncio.Lock()
        self._last_stats: SyncStats | None = None

    @property
    def state(self) -> SyncState:
        return self._state

    @property
    def last_stats(self) -> SyncStats | None:
        return self._last_stats

    def get_status(self) -> dict:
        return {
            "state": self._state.value,
            "last_stats": self._last_stats.to_json() if self._last_stats else None,
        }

    async def run_sync(self, mode: SyncMode | None = None) -> SyncStats:
        """Run a sync cycle. Raises if already syncing."""
        if self._lock.locked():
            raise RuntimeError("Sync already in progress")

        async with self._lock:
            self._state = SyncState.SYNCING
            try:
                stats = await self._do_sync(mode)
                self._state = SyncState.IDLE
                self._last_stats = stats
                return stats
            except Exception:
                self._state = SyncState.ERROR
                raise

    async def _do_sync(self, mode_override: SyncMode | None) -> SyncStats:
        # Determine mode
        last_run = await self._db.get_last_successful_sync()
        if last_run is None:
            effective_mode: SyncMode = "full"
        elif mode_override:
            effective_mode = mode_override
        else:
            effective_mode = self._config.sync.mode

        log.info("sync_start", mode=effective_mode)

        # Start DB sync run
        run = await self._db.start_sync_run(direction="bidirectional", mode=effective_mode)

        stats = SyncStats()
        try:
            sp_client = self._create_sp_client()
            ym_client = self._create_ym_client()

            async with sp_client, ym_client:
                # Ensure collections exist
                sp_col, ym_col = await self._ensure_collections()

                if effective_mode == "full":
                    await self._full_sync(sp_client, ym_client, sp_col.id, ym_col.id, stats)
                else:
                    since = (
                        datetime.fromisoformat(str(last_run.finished_at)) if last_run and last_run.finished_at else None
                    )
                    await self._incremental_sync(sp_client, ym_client, sp_col.id, ym_col.id, stats, since)

            await self._db.finish_sync_run(run.id, status="completed", stats_json=stats.to_json())
            log.info("sync_completed", stats=stats.to_json())
            return stats

        except Exception as exc:
            await self._db.finish_sync_run(run.id, status="failed", error_message=str(exc))
            log.error("sync_failed", error=str(exc))
            raise

    def _create_sp_client(self) -> SpotifyClient:
        if self._sp_factory:
            return self._sp_factory(self._config.spotify)
        from spondex.sync.spotify import SpotifyClient

        return SpotifyClient(self._config.spotify)

    def _create_ym_client(self) -> YandexClient:
        if self._ym_factory:
            return self._ym_factory(self._config.yandex)
        from spondex.sync.yandex import YandexClient

        return YandexClient(self._config.yandex)

    async def _ensure_collections(self):
        """Ensure 'liked' collections exist for both services, paired together."""
        sp_col = await self._db.find_collection(service="spotify", collection_type="liked")
        ym_col = await self._db.find_collection(service="yandex", collection_type="liked")

        if not sp_col:
            sp_col = await self._db.create_collection(service="spotify", collection_type="liked", title="Liked Songs")
        if not ym_col:
            ym_col = await self._db.create_collection(service="yandex", collection_type="liked", title="Liked Songs")

        if sp_col.paired_id is None or ym_col.paired_id is None:
            await self._db.pair_collections(sp_col.id, ym_col.id)
            sp_col = await self._db.get_collection(sp_col.id)
            ym_col = await self._db.get_collection(ym_col.id)

        return sp_col, ym_col

    # ── FULL SYNC ──────────────────────────────────────────────────────────

    async def _full_sync(self, sp, ym, sp_col_id, ym_col_id, stats):
        # 1. Fetch ALL tracks in parallel
        sp_tracks, ym_tracks = await asyncio.gather(sp.get_liked_tracks(), ym.get_liked_tracks())

        # 2. Load existing DB state
        db_sp_tracks = await self._db.list_collection_tracks(sp_col_id)
        db_ym_tracks = await self._db.list_collection_tracks(ym_col_id)

        # Build indexes: remote_id → mapping_id for existing tracks
        sp_mapping_ids = {ct.track_mapping_id for ct in db_sp_tracks}
        ym_mapping_ids = {ct.track_mapping_id for ct in db_ym_tracks}

        # Load all mappings for index building
        all_mapping_ids = list(sp_mapping_ids | ym_mapping_ids)
        mappings_by_id = await self._db.get_track_mappings_by_ids(all_mapping_ids)

        # Build remote_id → mapping indexes
        sp_id_to_mapping = {}
        ym_id_to_mapping = {}
        for m in mappings_by_id.values():
            if m.spotify_id:
                sp_id_to_mapping[m.spotify_id] = m
            if m.yandex_id:
                ym_id_to_mapping[m.yandex_id] = m

        # Compute new and removed
        remote_sp_ids = {t.remote_id for t in sp_tracks}
        remote_ym_ids = {t.remote_id for t in ym_tracks}

        sp_new = [t for t in sp_tracks if t.remote_id not in sp_id_to_mapping]
        ym_new = [t for t in ym_tracks if t.remote_id not in ym_id_to_mapping]

        sp_removed_mappings = [
            m
            for mid, m in mappings_by_id.items()
            if mid in sp_mapping_ids and m.spotify_id and m.spotify_id not in remote_sp_ids
        ]
        ym_removed_mappings = [
            m
            for mid, m in mappings_by_id.items()
            if mid in ym_mapping_ids and m.yandex_id and m.yandex_id not in remote_ym_ids
        ]

        # 3. Cross-match new tracks
        matches, unmatched_sp, unmatched_ym = cross_match(sp_new, ym_new)

        for match in matches:
            try:
                mapping = await self._db.upsert_track_mapping(
                    artist=match.spotify_track.artist,
                    title=match.spotify_track.title,
                    spotify_id=match.spotify_track.remote_id,
                    yandex_id=match.yandex_track.remote_id,
                    match_confidence=match.confidence,
                )
                await self._db.add_track_to_collection(
                    collection_id=sp_col_id,
                    track_mapping_id=mapping.id,
                    added_at=match.spotify_track.added_at,
                )
                await self._db.add_track_to_collection(
                    collection_id=ym_col_id,
                    track_mapping_id=mapping.id,
                    added_at=match.yandex_track.added_at,
                )
                stats.cross_matched += 1
            except Exception as exc:
                log.warning("cross_match_error", error=str(exc))
                stats.errors += 1

        # 4. Propagate removals (if enabled)
        if self._config.sync.propagate_deletions:
            for m in sp_removed_mappings:
                try:
                    await self._db.mark_track_removed(collection_id=sp_col_id, track_mapping_id=m.id)
                    if m.yandex_id:
                        await ym.unlike_tracks([m.yandex_id])
                        await self._db.mark_track_removed(collection_id=ym_col_id, track_mapping_id=m.id)
                    stats.sp_removed += 1
                except Exception as exc:
                    log.warning("sp_remove_error", error=str(exc))
                    stats.errors += 1

            for m in ym_removed_mappings:
                try:
                    await self._db.mark_track_removed(collection_id=ym_col_id, track_mapping_id=m.id)
                    if m.spotify_id:
                        await sp.remove_tracks([m.spotify_id])
                        await self._db.mark_track_removed(collection_id=sp_col_id, track_mapping_id=m.id)
                    stats.ym_removed += 1
                except Exception as exc:
                    log.warning("ym_remove_error", error=str(exc))
                    stats.errors += 1

        # 5. Propagate additions
        await self._propagate_additions(
            sp,
            ym,
            sp_col_id,
            ym_col_id,
            unmatched_sp,
            unmatched_ym,
            stats,
            existing_sp_ids=remote_sp_ids,
            existing_ym_ids=remote_ym_ids,
        )

        # 6. Retry unmatched
        await self._retry_unmatched(sp, ym, sp_col_id, ym_col_id, stats)

    # ── INCREMENTAL SYNC ───────────────────────────────────────────────────

    async def _incremental_sync(self, sp, ym, sp_col_id, ym_col_id, stats, since):
        # 1. Fetch new tracks only
        sp_tracks, ym_tracks = await asyncio.gather(
            sp.get_liked_tracks(since=since),
            ym.get_liked_tracks(since=since),
        )

        # 2. Cross-match
        matches, unmatched_sp, unmatched_ym = cross_match(sp_tracks, ym_tracks)

        for match in matches:
            try:
                mapping = await self._db.upsert_track_mapping(
                    artist=match.spotify_track.artist,
                    title=match.spotify_track.title,
                    spotify_id=match.spotify_track.remote_id,
                    yandex_id=match.yandex_track.remote_id,
                    match_confidence=match.confidence,
                )
                await self._db.add_track_to_collection(
                    collection_id=sp_col_id,
                    track_mapping_id=mapping.id,
                    added_at=match.spotify_track.added_at,
                )
                await self._db.add_track_to_collection(
                    collection_id=ym_col_id,
                    track_mapping_id=mapping.id,
                    added_at=match.yandex_track.added_at,
                )
                stats.cross_matched += 1
            except Exception as exc:
                log.warning("cross_match_error", error=str(exc))
                stats.errors += 1

        # 3. Propagate additions only (no removals in incremental)
        # Build existing ID sets from fetched tracks (for dedup)
        existing_sp = {t.remote_id for t in sp_tracks}
        existing_ym = {t.remote_id for t in ym_tracks}
        await self._propagate_additions(
            sp,
            ym,
            sp_col_id,
            ym_col_id,
            unmatched_sp,
            unmatched_ym,
            stats,
            existing_sp_ids=existing_sp,
            existing_ym_ids=existing_ym,
        )

    # ── SHARED HELPERS ─────────────────────────────────────────────────────

    _FUZZY_THRESHOLD = 0.8
    _DURATION_TOLERANCE_MS = 1000  # ±1 second

    @staticmethod
    def _is_good_match(
        query_artist: str,
        query_title: str,
        found_artist: str,
        found_title: str,
        *,
        query_duration_ms: int | None = None,
        found_duration_ms: int | None = None,
    ) -> bool:
        """Validate that a search result actually matches the query.

        Matching tiers (in order):
        1. Normalized exact/contains — accept immediately
        2. Transliterated exact/contains — accept immediately
        3. Fuzzy match (SequenceMatcher ratio >= 0.8) — accept, but if
           both tracks have duration and it differs by more than ±1s, reject
        """
        from difflib import SequenceMatcher

        q_artist = normalize(query_artist)
        q_title = normalize(query_title)
        f_artist = normalize(found_artist)
        f_title = normalize(found_title)

        def _contains(a: str, b: str) -> bool:
            return a == b or a in b or b in a

        def _fuzzy(a: str, b: str) -> float:
            return SequenceMatcher(None, a, b).ratio()

        # Tier 1: direct normalized comparison
        title_ok = _contains(q_title, f_title)
        artist_ok = _contains(q_artist, f_artist)
        if title_ok and artist_ok:
            return True

        # Tier 2: transliterated comparison
        qt_artist = transliterate(q_artist)
        ft_artist = transliterate(f_artist)
        qt_title = transliterate(q_title)
        ft_title = transliterate(f_title)

        t_artist_ok = artist_ok or _contains(qt_artist, ft_artist)
        t_title_ok = title_ok or _contains(qt_title, ft_title)
        if t_artist_ok and t_title_ok:
            return True

        # Tier 3: fuzzy matching with duration validation
        fuzzy_artist = max(
            _fuzzy(q_artist, f_artist),
            _fuzzy(qt_artist, ft_artist),
        )
        fuzzy_title = max(
            _fuzzy(q_title, f_title),
            _fuzzy(qt_title, ft_title),
        )

        # Both artist and title must pass fuzzy threshold
        if fuzzy_artist < SyncEngine._FUZZY_THRESHOLD or fuzzy_title < SyncEngine._FUZZY_THRESHOLD:
            return False

        # Duration veto: if both known, must be within tolerance
        return not (
            query_duration_ms is not None
            and found_duration_ms is not None
            and abs(query_duration_ms - found_duration_ms) > SyncEngine._DURATION_TOLERANCE_MS
        )

    async def _propagate_additions(
        self,
        sp,
        ym,
        sp_col_id,
        ym_col_id,
        unmatched_sp,
        unmatched_ym,
        stats,
        *,
        existing_sp_ids: set[str] | None = None,
        existing_ym_ids: set[str] | None = None,
    ):
        """Propagate unmatched tracks: search on the other service and add."""
        existing_sp_ids = existing_sp_ids or set()
        existing_ym_ids = existing_ym_ids or set()

        # Spotify → Yandex
        for track in unmatched_sp:
            try:
                mapping = await self._db.upsert_track_mapping(
                    artist=track.artist,
                    title=track.title,
                    spotify_id=track.remote_id,
                )
                await self._db.add_track_to_collection(
                    collection_id=sp_col_id,
                    track_mapping_id=mapping.id,
                    added_at=track.added_at,
                )

                found = await ym.search_track(track.artist, track.title)
                if found and self._is_good_match(
                    track.artist,
                    track.title,
                    found.artist,
                    found.title,
                    query_duration_ms=track.duration_ms,
                    found_duration_ms=found.duration_ms,
                ):
                    already_liked = found.remote_id in existing_ym_ids
                    mapping = await self._db.upsert_track_mapping(
                        artist=track.artist,
                        title=track.title,
                        spotify_id=track.remote_id,
                        yandex_id=found.remote_id,
                    )
                    if not already_liked:
                        await ym.like_tracks([found.remote_id])
                        stats.ym_added += 1
                    await self._db.add_track_to_collection(
                        collection_id=ym_col_id,
                        track_mapping_id=mapping.id,
                        added_at=found.added_at,
                    )
                    existing_ym_ids.add(found.remote_id)
                else:
                    if found:
                        log.info(
                            "search_mismatch",
                            direction="sp→ym",
                            query=f"{track.artist} — {track.title}",
                            found=f"{found.artist} — {found.title}",
                        )
                    await self._db.add_unmatched(
                        source_service="spotify",
                        source_id=track.remote_id,
                        artist=track.artist,
                        title=track.title,
                    )
                    stats.unmatched += 1
            except Exception as exc:
                log.warning("sp_propagate_error", error=str(exc))
                stats.errors += 1

        # Yandex → Spotify
        for track in unmatched_ym:
            try:
                mapping = await self._db.upsert_track_mapping(
                    artist=track.artist,
                    title=track.title,
                    yandex_id=track.remote_id,
                )
                await self._db.add_track_to_collection(
                    collection_id=ym_col_id,
                    track_mapping_id=mapping.id,
                    added_at=track.added_at,
                )

                found = await sp.search_track(track.artist, track.title)
                if found and self._is_good_match(
                    track.artist,
                    track.title,
                    found.artist,
                    found.title,
                    query_duration_ms=track.duration_ms,
                    found_duration_ms=found.duration_ms,
                ):
                    already_saved = found.remote_id in existing_sp_ids
                    mapping = await self._db.upsert_track_mapping(
                        artist=track.artist,
                        title=track.title,
                        spotify_id=found.remote_id,
                        yandex_id=track.remote_id,
                    )
                    if not already_saved:
                        await sp.save_tracks([found.remote_id])
                        stats.sp_added += 1
                    await self._db.add_track_to_collection(
                        collection_id=sp_col_id,
                        track_mapping_id=mapping.id,
                        added_at=found.added_at,
                    )
                    existing_sp_ids.add(found.remote_id)
                else:
                    if found:
                        log.info(
                            "search_mismatch",
                            direction="ym→sp",
                            query=f"{track.artist} — {track.title}",
                            found=f"{found.artist} — {found.title}",
                        )
                    await self._db.add_unmatched(
                        source_service="yandex",
                        source_id=track.remote_id,
                        artist=track.artist,
                        title=track.title,
                    )
                    stats.unmatched += 1
            except Exception as exc:
                log.warning("ym_propagate_error", error=str(exc))
                stats.errors += 1

    async def _retry_unmatched(self, sp, ym, sp_col_id, ym_col_id, stats):
        """Retry previously unmatched tracks (full sync only)."""
        for source_service, client, target_col_id, add_fn, _source_col_id in [
            ("spotify", ym, ym_col_id, ym.like_tracks, sp_col_id),
            ("yandex", sp, sp_col_id, sp.save_tracks, ym_col_id),
        ]:
            unmatched_list = await self._db.list_unmatched(source_service)
            for um in unmatched_list:
                if um.attempts >= _MAX_UNMATCHED_ATTEMPTS:
                    continue
                try:
                    found = await client.search_track(um.artist, um.title)
                    if found and self._is_good_match(um.artist, um.title, found.artist, found.title):
                        id_kw = (
                            {"yandex_id": found.remote_id}
                            if source_service == "spotify"
                            else {"spotify_id": found.remote_id}
                        )
                        mapping = await self._db.upsert_track_mapping(
                            artist=um.artist,
                            title=um.title,
                            **{f"{source_service}_id": um.source_id},
                            **id_kw,
                        )
                        await add_fn([found.remote_id])
                        await self._db.add_track_to_collection(
                            collection_id=target_col_id,
                            track_mapping_id=mapping.id,
                        )
                        await self._db.resolve_unmatched(source_service, um.source_id)
                        stats.retried_ok += 1
                    else:
                        # Bump attempt counter
                        await self._db.add_unmatched(
                            source_service=source_service,
                            source_id=um.source_id,
                            artist=um.artist,
                            title=um.title,
                        )
                except Exception as exc:
                    log.warning("retry_unmatched_error", error=str(exc))
                    stats.errors += 1
