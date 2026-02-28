"""Tests for the Spondex storage layer."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio

from spondex.storage import Database


@pytest_asyncio.fixture()
async def db(tmp_path):
    """Provide a fresh in-memory-like database for each test."""
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


# ---------------------------------------------------------------------------
# Schema / connect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_connect_creates_tables(db: Database):
    cur = await db.conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row["name"] for row in await cur.fetchall()}
    assert tables >= {"track_mapping", "collection", "collection_track", "unmatched", "sync_runs"}


@pytest.mark.asyncio()
async def test_foreign_keys_enabled(db: Database):
    cur = await db.conn.execute("PRAGMA foreign_keys")
    row = await cur.fetchone()
    assert row[0] == 1


# ---------------------------------------------------------------------------
# track_mapping CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_upsert_track_mapping_insert(db: Database):
    tm = await db.upsert_track_mapping(artist="Radiohead", title="Creep", spotify_id="sp_1")
    assert tm.id is not None
    assert tm.artist == "Radiohead"
    assert tm.spotify_id == "sp_1"
    assert tm.yandex_id is None
    assert tm.match_confidence == 1.0


@pytest.mark.asyncio()
async def test_upsert_track_mapping_update_adds_yandex(db: Database):
    tm1 = await db.upsert_track_mapping(artist="Radiohead", title="Creep", spotify_id="sp_1")
    tm2 = await db.upsert_track_mapping(artist="Radiohead", title="Creep", spotify_id="sp_1", yandex_id="ya_1")
    assert tm2.id == tm1.id
    assert tm2.yandex_id == "ya_1"
    assert tm2.spotify_id == "sp_1"


@pytest.mark.asyncio()
async def test_find_track_mapping_by_spotify(db: Database):
    await db.upsert_track_mapping(artist="Muse", title="Hysteria", spotify_id="sp_2", yandex_id="ya_2")
    found = await db.find_track_mapping(spotify_id="sp_2")
    assert found is not None
    assert found.artist == "Muse"


@pytest.mark.asyncio()
async def test_find_track_mapping_by_yandex(db: Database):
    await db.upsert_track_mapping(artist="Muse", title="Hysteria", spotify_id="sp_2", yandex_id="ya_2")
    found = await db.find_track_mapping(yandex_id="ya_2")
    assert found is not None
    assert found.title == "Hysteria"


@pytest.mark.asyncio()
async def test_find_track_mapping_not_found(db: Database):
    found = await db.find_track_mapping(spotify_id="nonexistent")
    assert found is None


@pytest.mark.asyncio()
async def test_list_track_mappings(db: Database):
    await db.upsert_track_mapping(artist="A", title="1", spotify_id="sp_a")
    await db.upsert_track_mapping(artist="B", title="2", yandex_id="ya_b")
    mappings = await db.list_track_mappings()
    assert len(mappings) == 2


@pytest.mark.asyncio()
async def test_get_track_mapping_by_id(db: Database):
    tm = await db.upsert_track_mapping(artist="X", title="Y", spotify_id="sp_x")
    fetched = await db.get_track_mapping_by_id(tm.id)
    assert fetched is not None
    assert fetched.artist == "X"


# ---------------------------------------------------------------------------
# collection CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_create_liked_collections(db: Database):
    sp = await db.create_collection(service="spotify", collection_type="liked", title="Liked Songs")
    ya = await db.create_collection(service="yandex", collection_type="liked", title="Мне нравится")
    assert sp.id is not None
    assert ya.id is not None
    assert sp.id != ya.id


@pytest.mark.asyncio()
async def test_find_liked_collection(db: Database):
    await db.create_collection(service="spotify", collection_type="liked", title="Liked Songs")
    found = await db.find_collection(service="spotify", collection_type="liked")
    assert found is not None
    assert found.title == "Liked Songs"


@pytest.mark.asyncio()
async def test_create_playlist_collection(db: Database):
    pl = await db.create_collection(
        service="spotify",
        collection_type="playlist",
        remote_id="pl_abc",
        title="Chill Vibes",
    )
    assert pl.remote_id == "pl_abc"


@pytest.mark.asyncio()
async def test_pair_collections(db: Database):
    sp = await db.create_collection(service="spotify", collection_type="liked", title="Liked Songs")
    ya = await db.create_collection(service="yandex", collection_type="liked", title="Мне нравится")
    await db.pair_collections(sp.id, ya.id)

    sp_updated = await db.get_collection(sp.id)
    ya_updated = await db.get_collection(ya.id)
    assert sp_updated.paired_id == ya.id
    assert ya_updated.paired_id == sp.id


@pytest.mark.asyncio()
async def test_list_collections_by_service(db: Database):
    await db.create_collection(service="spotify", collection_type="liked", title="Liked")
    await db.create_collection(service="yandex", collection_type="liked", title="Liked")
    await db.create_collection(service="spotify", collection_type="playlist", remote_id="pl1", title="My PL")
    sp_cols = await db.list_collections(service="spotify")
    assert len(sp_cols) == 2
    all_cols = await db.list_collections()
    assert len(all_cols) == 3


# ---------------------------------------------------------------------------
# collection_track CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_add_track_to_collection(db: Database):
    col = await db.create_collection(service="spotify", collection_type="liked", title="Liked")
    tm = await db.upsert_track_mapping(artist="A", title="B", spotify_id="sp_1")
    ct = await db.add_track_to_collection(collection_id=col.id, track_mapping_id=tm.id, position=0)
    assert ct.collection_id == col.id
    assert ct.track_mapping_id == tm.id
    assert ct.removed_at is None
    assert ct.synced_at is not None


@pytest.mark.asyncio()
async def test_mark_track_removed_and_list(db: Database):
    col = await db.create_collection(service="spotify", collection_type="liked", title="Liked")
    tm = await db.upsert_track_mapping(artist="A", title="B", spotify_id="sp_1")
    await db.add_track_to_collection(collection_id=col.id, track_mapping_id=tm.id)

    await db.mark_track_removed(collection_id=col.id, track_mapping_id=tm.id)

    active = await db.list_collection_tracks(col.id)
    assert len(active) == 0

    all_tracks = await db.list_collection_tracks(col.id, include_removed=True)
    assert len(all_tracks) == 1
    assert all_tracks[0].removed_at is not None


@pytest.mark.asyncio()
async def test_readd_removed_track_clears_removed_at(db: Database):
    col = await db.create_collection(service="spotify", collection_type="liked", title="Liked")
    tm = await db.upsert_track_mapping(artist="A", title="B", spotify_id="sp_1")
    await db.add_track_to_collection(collection_id=col.id, track_mapping_id=tm.id)
    await db.mark_track_removed(collection_id=col.id, track_mapping_id=tm.id)

    # Re-add should clear removed_at
    ct = await db.add_track_to_collection(collection_id=col.id, track_mapping_id=tm.id)
    assert ct.removed_at is None


@pytest.mark.asyncio()
async def test_delete_removed_tracks(db: Database):
    col = await db.create_collection(service="spotify", collection_type="liked", title="Liked")
    tm1 = await db.upsert_track_mapping(artist="A", title="1", spotify_id="sp_1")
    tm2 = await db.upsert_track_mapping(artist="B", title="2", spotify_id="sp_2")

    await db.add_track_to_collection(collection_id=col.id, track_mapping_id=tm1.id)
    await db.add_track_to_collection(collection_id=col.id, track_mapping_id=tm2.id)
    await db.mark_track_removed(collection_id=col.id, track_mapping_id=tm1.id)

    deleted = await db.delete_removed_tracks(col.id)
    assert deleted == 1

    all_tracks = await db.list_collection_tracks(col.id, include_removed=True)
    assert len(all_tracks) == 1


# ---------------------------------------------------------------------------
# unmatched CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_add_unmatched(db: Database):
    um = await db.add_unmatched(source_service="spotify", source_id="sp_99", artist="Unknown", title="Song")
    assert um.id is not None
    assert um.attempts == 1


@pytest.mark.asyncio()
async def test_add_unmatched_increments_attempts(db: Database):
    await db.add_unmatched(source_service="spotify", source_id="sp_99", artist="Unknown", title="Song")
    um2 = await db.add_unmatched(source_service="spotify", source_id="sp_99", artist="Unknown", title="Song")
    assert um2.attempts == 2


@pytest.mark.asyncio()
async def test_resolve_unmatched(db: Database):
    await db.add_unmatched(source_service="spotify", source_id="sp_99", artist="X", title="Y")
    await db.resolve_unmatched("spotify", "sp_99")
    remaining = await db.list_unmatched(source_service="spotify")
    assert len(remaining) == 0


@pytest.mark.asyncio()
async def test_list_unmatched_filters_by_service(db: Database):
    await db.add_unmatched(source_service="spotify", source_id="sp_1", artist="A", title="1")
    await db.add_unmatched(source_service="yandex", source_id="ya_1", artist="B", title="2")
    sp = await db.list_unmatched(source_service="spotify")
    assert len(sp) == 1
    all_um = await db.list_unmatched()
    assert len(all_um) == 2


# ---------------------------------------------------------------------------
# sync_runs CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_start_and_finish_sync_run(db: Database):
    run = await db.start_sync_run(direction="bidirectional", mode="full")
    assert run.status == "running"
    assert run.started_at is not None
    assert run.finished_at is None

    stats = json.dumps({"added": 5, "removed": 1, "failed": 0})
    finished = await db.finish_sync_run(run.id, status="completed", stats_json=stats)
    assert finished.status == "completed"
    assert finished.finished_at is not None
    assert json.loads(finished.stats_json) == {"added": 5, "removed": 1, "failed": 0}


@pytest.mark.asyncio()
async def test_sync_run_with_collection(db: Database):
    col = await db.create_collection(service="spotify", collection_type="liked", title="Liked")
    run = await db.start_sync_run(direction="spotify_to_yandex", mode="incremental", collection_id=col.id)
    assert run.collection_id == col.id


@pytest.mark.asyncio()
async def test_sync_run_failed(db: Database):
    run = await db.start_sync_run(direction="bidirectional", mode="full")
    finished = await db.finish_sync_run(run.id, status="failed", error_message="API rate limit exceeded")
    assert finished.status == "failed"
    assert finished.error_message == "API rate limit exceeded"


@pytest.mark.asyncio()
async def test_list_sync_runs_ordered_desc(db: Database):
    r1 = await db.start_sync_run(direction="bidirectional", mode="full")
    await db.finish_sync_run(r1.id, status="completed")
    r2 = await db.start_sync_run(direction="bidirectional", mode="incremental")
    await db.finish_sync_run(r2.id, status="completed")

    runs = await db.list_sync_runs(limit=10)
    assert len(runs) == 2
    assert runs[0].id > runs[1].id  # newest first


# ---------------------------------------------------------------------------
# Round-trip / integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_full_sync_scenario(db: Database):
    """Simulate a real liked-tracks sync: create collections, map tracks, sync."""
    # 1. Create paired liked collections
    sp_liked = await db.create_collection(service="spotify", collection_type="liked", title="Liked Songs")
    ya_liked = await db.create_collection(service="yandex", collection_type="liked", title="Мне нравится")
    await db.pair_collections(sp_liked.id, ya_liked.id)

    # 2. Start sync run
    run = await db.start_sync_run(direction="bidirectional", mode="full")

    # 3. Map a track found on both platforms
    tm = await db.upsert_track_mapping(
        artist="Radiohead",
        title="Creep",
        spotify_id="sp_creep",
        yandex_id="ya_creep",
        match_confidence=0.95,
    )

    # 4. Add to both collections
    await db.add_track_to_collection(collection_id=sp_liked.id, track_mapping_id=tm.id, position=0)
    await db.add_track_to_collection(collection_id=ya_liked.id, track_mapping_id=tm.id, position=0)

    # 5. Track we couldn't find on Yandex
    await db.add_unmatched(
        source_service="spotify",
        source_id="sp_rare",
        artist="Obscure Band",
        title="Rare Song",
    )

    # 6. Finish sync
    stats = json.dumps({"added": 1, "unmatched": 1})
    finished = await db.finish_sync_run(run.id, status="completed", stats_json=stats)

    # Verify final state
    sp_tracks = await db.list_collection_tracks(sp_liked.id)
    assert len(sp_tracks) == 1
    assert sp_tracks[0].track_mapping_id == tm.id

    unmatched = await db.list_unmatched(source_service="spotify")
    assert len(unmatched) == 1
    assert unmatched[0].artist == "Obscure Band"

    runs = await db.list_sync_runs()
    assert len(runs) == 1
    assert runs[0].status == "completed"
    assert finished.finished_at is not None


@pytest.mark.asyncio()
async def test_reconnect(tmp_path):
    """Data persists across connect/close cycles."""
    path = tmp_path / "persist.db"

    db1 = Database(path)
    await db1.connect()
    await db1.upsert_track_mapping(artist="A", title="B", spotify_id="sp_1")
    await db1.close()

    db2 = Database(path)
    await db2.connect()
    found = await db2.find_track_mapping(spotify_id="sp_1")
    assert found is not None
    assert found.artist == "A"
    await db2.close()
