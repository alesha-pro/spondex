"""Tests for the SyncEngine — full and incremental sync flows."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from spondex.config import AppConfig, SpotifyConfig, SyncConfig, YandexConfig
from spondex.storage.database import Database
from spondex.sync.differ import RemoteTrack
from spondex.sync.engine import SyncEngine, SyncState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sp_track(remote_id: str, artist: str, title: str, added_at=None) -> RemoteTrack:
    return RemoteTrack(
        service="spotify", remote_id=remote_id, artist=artist, title=title, added_at=added_at
    )


def _ym_track(remote_id: str, artist: str, title: str, added_at=None) -> RemoteTrack:
    return RemoteTrack(
        service="yandex", remote_id=remote_id, artist=artist, title=title, added_at=added_at
    )


class MockClient:
    """Mock client that implements the SpotifyClient/YandexClient protocol."""

    def __init__(self, liked_tracks=None, search_results=None):
        self.liked_tracks = liked_tracks or []
        self.search_results = search_results or {}  # "artist title" → RemoteTrack
        self.saved_ids: list[str] = []
        self.removed_ids: list[str] = []
        self.liked_ids: list[str] = []
        self.unliked_ids: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    async def get_liked_tracks(self, *, since=None):
        return self.liked_tracks

    async def save_tracks(self, ids):
        self.saved_ids.extend(ids)

    async def remove_tracks(self, ids):
        self.removed_ids.extend(ids)

    async def like_tracks(self, ids):
        self.liked_ids.extend(ids)

    async def unlike_tracks(self, ids):
        self.unliked_ids.extend(ids)

    async def search_track(self, artist, title):
        return self.search_results.get(f"{artist} {title}")


def _make_config(**sync_kw) -> AppConfig:
    return AppConfig(
        spotify=SpotifyConfig(
            client_id="test",
            client_secret="test",
            refresh_token="test",
        ),
        yandex=YandexConfig(token="test"),
        sync=SyncConfig(**sync_kw),
    )


def _mock_factory(client):
    """Return a factory callable that ignores config and returns the mock client."""
    def factory(config):
        return client
    return factory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def db(tmp_path):
    d = Database(tmp_path / "test.db")
    await d.connect()
    yield d
    await d.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_sync_forces_full(db):
    """First sync (no previous runs) should force full mode."""
    sp = MockClient(liked_tracks=[
        _sp_track("sp1", "Artist A", "Song One"),
    ])
    ym = MockClient(
        liked_tracks=[],
        search_results={
            "Artist A Song One": _ym_track("ym1", "Artist A", "Song One"),
        },
    )

    engine = SyncEngine(
        _make_config(mode="incremental"),
        db,
        sp_factory=_mock_factory(sp),
        ym_factory=_mock_factory(ym),
    )
    stats = await engine.run_sync()

    assert stats.ym_added == 1
    assert ym.liked_ids == ["ym1"]


@pytest.mark.asyncio
async def test_cross_match_first_sync(db):
    """Tracks present on both sides should be cross-matched without search."""
    sp = MockClient(liked_tracks=[
        _sp_track("sp1", "Artist A", "Song One"),
        _sp_track("sp2", "Artist B", "Song Two"),
    ])
    ym = MockClient(liked_tracks=[
        _ym_track("ym1", "Artist A", "Song One"),
    ])

    engine = SyncEngine(
        _make_config(),
        db,
        sp_factory=_mock_factory(sp),
        ym_factory=_mock_factory(ym),
    )
    stats = await engine.run_sync()

    assert stats.cross_matched == 1
    # sp2 unmatched → add_unmatched (no search result for Yandex)
    assert stats.unmatched == 1


@pytest.mark.asyncio
async def test_propagate_additions_both_directions(db):
    """New tracks on each side should be propagated to the other."""
    sp = MockClient(
        liked_tracks=[_sp_track("sp1", "Art", "Song")],
        search_results={
            "YmArt YmSong": _sp_track("sp_found", "YmArt", "YmSong"),
        },
    )
    ym = MockClient(
        liked_tracks=[_ym_track("ym1", "YmArt", "YmSong")],
        search_results={
            "Art Song": _ym_track("ym_found", "Art", "Song"),
        },
    )

    engine = SyncEngine(
        _make_config(),
        db,
        sp_factory=_mock_factory(sp),
        ym_factory=_mock_factory(ym),
    )
    stats = await engine.run_sync()

    assert stats.ym_added == 1  # sp→ym
    assert stats.sp_added == 1  # ym→sp
    assert ym.liked_ids == ["ym_found"]
    assert sp.saved_ids == ["sp_found"]


@pytest.mark.asyncio
async def test_full_sync_removals(db):
    """Full sync should propagate deletions when enabled."""
    # Pre-populate DB with a known mapping
    sp = MockClient(liked_tracks=[])  # track removed from Spotify
    ym = MockClient(liked_tracks=[])

    engine = SyncEngine(
        _make_config(propagate_deletions=True),
        db,
        sp_factory=_mock_factory(sp),
        ym_factory=_mock_factory(ym),
    )

    # First: seed DB with a track on both sides
    mapping = await db.upsert_track_mapping(
        artist="Art", title="Song", spotify_id="sp1", yandex_id="ym1"
    )
    sp_col = await db.create_collection(
        service="spotify", collection_type="liked", title="Liked Songs"
    )
    ym_col = await db.create_collection(
        service="yandex", collection_type="liked", title="Liked Songs"
    )
    await db.pair_collections(sp_col.id, ym_col.id)
    await db.add_track_to_collection(
        collection_id=sp_col.id, track_mapping_id=mapping.id
    )
    await db.add_track_to_collection(
        collection_id=ym_col.id, track_mapping_id=mapping.id
    )

    stats = await engine.run_sync(mode="full")

    # Track removed from Spotify → should unlike on Yandex
    assert stats.sp_removed == 1
    assert ym.unliked_ids == ["ym1"]


@pytest.mark.asyncio
async def test_incremental_no_removals(db):
    """Incremental sync should NOT process removals."""
    sp = MockClient(liked_tracks=[])
    ym = MockClient(liked_tracks=[])

    engine = SyncEngine(
        _make_config(),
        db,
        sp_factory=_mock_factory(sp),
        ym_factory=_mock_factory(ym),
    )

    # Seed a completed sync run so incremental mode is used
    run = await db.start_sync_run(direction="bidirectional", mode="full")
    await db.finish_sync_run(run.id, status="completed")

    # Seed a mapping that would be "removed"
    mapping = await db.upsert_track_mapping(
        artist="Art", title="Song", spotify_id="sp1", yandex_id="ym1"
    )
    sp_col = await db.create_collection(
        service="spotify", collection_type="liked", title="Liked Songs"
    )
    ym_col = await db.create_collection(
        service="yandex", collection_type="liked", title="Liked Songs"
    )
    await db.pair_collections(sp_col.id, ym_col.id)
    await db.add_track_to_collection(
        collection_id=sp_col.id, track_mapping_id=mapping.id
    )

    stats = await engine.run_sync()  # should be incremental

    assert stats.sp_removed == 0
    assert stats.ym_removed == 0
    assert ym.unliked_ids == []


@pytest.mark.asyncio
async def test_sync_error_state(db):
    """Engine should transition to ERROR state on failure."""

    class FailClient(MockClient):
        async def get_liked_tracks(self, **kw):
            raise RuntimeError("Auth failed")

    engine = SyncEngine(
        _make_config(),
        db,
        sp_factory=_mock_factory(FailClient()),
        ym_factory=_mock_factory(MockClient()),
    )

    with pytest.raises(RuntimeError, match="Auth failed"):
        await engine.run_sync()

    assert engine.state == SyncState.ERROR


@pytest.mark.asyncio
async def test_concurrent_sync_blocked(db):
    """Concurrent sync attempts should raise."""
    syncing = asyncio.Event()
    proceed = asyncio.Event()

    class SlowClient(MockClient):
        async def get_liked_tracks(self, **kw):
            syncing.set()
            await proceed.wait()
            return []

    engine = SyncEngine(
        _make_config(),
        db,
        sp_factory=_mock_factory(SlowClient()),
        ym_factory=_mock_factory(MockClient()),
    )

    task = asyncio.create_task(engine.run_sync())
    await syncing.wait()

    with pytest.raises(RuntimeError, match="already in progress"):
        await engine.run_sync()

    proceed.set()
    await task


@pytest.mark.asyncio
async def test_retry_unmatched(db):
    """Full sync should retry previously unmatched tracks."""
    # Pre-populate an unmatched entry
    await db.add_unmatched(
        source_service="spotify", source_id="sp1", artist="Art", title="Song"
    )

    sp = MockClient(liked_tracks=[])
    ym = MockClient(
        liked_tracks=[],
        search_results={"Art Song": _ym_track("ym_found", "Art", "Song")},
    )

    engine = SyncEngine(
        _make_config(),
        db,
        sp_factory=_mock_factory(sp),
        ym_factory=_mock_factory(ym),
    )
    stats = await engine.run_sync(mode="full")

    assert stats.retried_ok == 1
    assert ym.liked_ids == ["ym_found"]

    # Unmatched should be resolved
    remaining = await db.list_unmatched("spotify")
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_get_status(db):
    """get_status should return engine state info."""
    engine = SyncEngine(
        _make_config(),
        db,
        sp_factory=_mock_factory(MockClient()),
        ym_factory=_mock_factory(MockClient()),
    )
    status = engine.get_status()
    assert status["state"] == "idle"
    assert status["last_stats"] is None


# ---------------------------------------------------------------------------
# _is_good_match tests
# ---------------------------------------------------------------------------


def test_is_good_match_exact():
    """Exact normalized match should pass."""
    assert SyncEngine._is_good_match("Radiohead", "Creep", "radiohead", "creep")


def test_is_good_match_contains():
    """Substring/contains match should pass."""
    assert SyncEngine._is_good_match("DJ Snake", "Turn Down", "DJ Snake", "Turn Down for What")


def test_is_good_match_transliteration():
    """Cyrillic ↔ Latin via transliteration should pass."""
    assert SyncEngine._is_good_match("Паша Панамо", "Лунный город", "Pasha Panamo", "Lunnyy gorod")


def test_is_good_match_fuzzy_close():
    """Fuzzy match for close but non-exact names (Смоки→smoki vs smoky)."""
    # "smoki mo" vs "smoky mo" — ratio ~0.93, should pass
    assert SyncEngine._is_good_match(
        "Смоки Мо", "Потерянный рай", "Smoky Mo", "Потерянный рай"
    )


def test_is_good_match_fuzzy_with_matching_duration():
    """Fuzzy match + matching duration should pass."""
    assert SyncEngine._is_good_match(
        "Смоки Мо", "Потерянный рай", "Smoky Mo", "Потерянный рай",
        query_duration_ms=240000,
        found_duration_ms=240500,  # within ±1s
    )


def test_is_good_match_fuzzy_with_mismatched_duration():
    """Fuzzy match + mismatched duration should fail."""
    assert not SyncEngine._is_good_match(
        "Смоки Мо", "Потерянный рай", "Smoky Mo", "Совсем другая песня",
        query_duration_ms=240000,
        found_duration_ms=180000,  # 60s difference
    )


def test_is_good_match_duration_ignored_for_exact():
    """Duration is NOT checked for exact/contains matches."""
    # Exact match with wildly different duration — still passes
    assert SyncEngine._is_good_match(
        "Artist", "Song", "Artist", "Song",
        query_duration_ms=100000,
        found_duration_ms=300000,
    )


def test_is_good_match_rejects_unrelated():
    """Completely unrelated tracks should not match."""
    assert not SyncEngine._is_good_match("Radiohead", "Creep", "Drake", "Hotline Bling")


def test_is_good_match_fuzzy_duration_tolerance_boundary():
    """Duration exactly at ±1s boundary should pass."""
    assert SyncEngine._is_good_match(
        "Смоки Мо", "Потерянный рай", "Smoky Mo", "Потерянный рай",
        query_duration_ms=240000,
        found_duration_ms=241000,  # exactly 1s difference
    )
