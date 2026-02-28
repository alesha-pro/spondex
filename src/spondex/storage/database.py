"""Async SQLite database for the Spondex storage layer."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from spondex.storage.models import (
    Collection,
    CollectionTrack,
    SyncRun,
    TrackMapping,
    Unmatched,
)

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS track_mapping (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spotify_id TEXT,
    yandex_id TEXT,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    match_confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (spotify_id IS NOT NULL OR yandex_id IS NOT NULL),
    UNIQUE(spotify_id),
    UNIQUE(yandex_id)
);

CREATE TABLE IF NOT EXISTS collection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL CHECK(service IN ('spotify', 'yandex')),
    collection_type TEXT NOT NULL CHECK(collection_type IN ('liked', 'playlist', 'album')),
    remote_id TEXT,
    title TEXT NOT NULL,
    paired_id INTEGER REFERENCES collection(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(service, collection_type, remote_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_liked_per_service
    ON collection(service) WHERE collection_type = 'liked';

CREATE TABLE IF NOT EXISTS collection_track (
    collection_id INTEGER NOT NULL REFERENCES collection(id),
    track_mapping_id INTEGER NOT NULL REFERENCES track_mapping(id),
    position INTEGER,
    added_at TEXT,
    synced_at TEXT,
    removed_at TEXT,
    UNIQUE(collection_id, track_mapping_id)
);

CREATE TABLE IF NOT EXISTS unmatched (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_service TEXT NOT NULL CHECK(source_service IN ('spotify', 'yandex')),
    source_id TEXT NOT NULL,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 1,
    last_attempt_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_service, source_id)
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    collection_id INTEGER REFERENCES collection(id),
    direction TEXT NOT NULL CHECK(direction IN (
        'spotify_to_yandex', 'yandex_to_spotify', 'bidirectional'
    )),
    mode TEXT NOT NULL CHECK(mode IN ('full', 'incremental')),
    status TEXT NOT NULL CHECK(status IN (
        'running', 'completed', 'failed', 'cancelled'
    )),
    stats_json TEXT,
    error_message TEXT
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Async SQLite database wrapper for Spondex."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            msg = "Database not connected. Call connect() first."
            raise RuntimeError(msg)
        return self._conn

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # -- track_mapping --------------------------------------------------------

    async def upsert_track_mapping(
        self,
        *,
        artist: str,
        title: str,
        spotify_id: str | None = None,
        yandex_id: str | None = None,
        match_confidence: float = 1.0,
    ) -> TrackMapping:
        now = _now_iso()
        cur = await self.conn.execute(
            """
            INSERT INTO track_mapping (spotify_id, yandex_id, artist, title, match_confidence, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (spotify_id) DO UPDATE SET
                yandex_id = COALESCE(excluded.yandex_id, track_mapping.yandex_id),
                artist = excluded.artist,
                title = excluded.title,
                match_confidence = excluded.match_confidence,
                updated_at = excluded.updated_at
            ON CONFLICT (yandex_id) DO UPDATE SET
                spotify_id = COALESCE(excluded.spotify_id, track_mapping.spotify_id),
                artist = excluded.artist,
                title = excluded.title,
                match_confidence = excluded.match_confidence,
                updated_at = excluded.updated_at
            RETURNING *
            """,
            (spotify_id, yandex_id, artist, title, match_confidence, now, now),
        )
        row = await cur.fetchone()
        await self.conn.commit()
        return self._row_to_track_mapping(row)

    async def get_track_mapping_by_id(self, mapping_id: int) -> TrackMapping | None:
        cur = await self.conn.execute(
            "SELECT * FROM track_mapping WHERE id = ?", (mapping_id,)
        )
        row = await cur.fetchone()
        return self._row_to_track_mapping(row) if row else None

    async def find_track_mapping(
        self,
        *,
        spotify_id: str | None = None,
        yandex_id: str | None = None,
    ) -> TrackMapping | None:
        if spotify_id:
            cur = await self.conn.execute(
                "SELECT * FROM track_mapping WHERE spotify_id = ?", (spotify_id,)
            )
        elif yandex_id:
            cur = await self.conn.execute(
                "SELECT * FROM track_mapping WHERE yandex_id = ?", (yandex_id,)
            )
        else:
            return None
        row = await cur.fetchone()
        return self._row_to_track_mapping(row) if row else None

    async def list_track_mappings(self) -> list[TrackMapping]:
        cur = await self.conn.execute("SELECT * FROM track_mapping ORDER BY id")
        rows = await cur.fetchall()
        return [self._row_to_track_mapping(r) for r in rows]

    # -- collection -----------------------------------------------------------

    async def create_collection(
        self,
        *,
        service: str,
        collection_type: str,
        title: str,
        remote_id: str | None = None,
        paired_id: int | None = None,
    ) -> Collection:
        cur = await self.conn.execute(
            """
            INSERT INTO collection (service, collection_type, remote_id, title, paired_id)
            VALUES (?, ?, ?, ?, ?)
            RETURNING *
            """,
            (service, collection_type, remote_id, title, paired_id),
        )
        row = await cur.fetchone()
        await self.conn.commit()
        return self._row_to_collection(row)

    async def get_collection(self, collection_id: int) -> Collection | None:
        cur = await self.conn.execute(
            "SELECT * FROM collection WHERE id = ?", (collection_id,)
        )
        row = await cur.fetchone()
        return self._row_to_collection(row) if row else None

    async def find_collection(
        self,
        *,
        service: str,
        collection_type: str,
        remote_id: str | None = None,
    ) -> Collection | None:
        if collection_type == "liked":
            cur = await self.conn.execute(
                "SELECT * FROM collection WHERE service = ? AND collection_type = 'liked'",
                (service,),
            )
        else:
            cur = await self.conn.execute(
                "SELECT * FROM collection WHERE service = ? AND collection_type = ? AND remote_id = ?",
                (service, collection_type, remote_id),
            )
        row = await cur.fetchone()
        return self._row_to_collection(row) if row else None

    async def list_collections(self, service: str | None = None) -> list[Collection]:
        if service:
            cur = await self.conn.execute(
                "SELECT * FROM collection WHERE service = ? ORDER BY id", (service,)
            )
        else:
            cur = await self.conn.execute("SELECT * FROM collection ORDER BY id")
        rows = await cur.fetchall()
        return [self._row_to_collection(r) for r in rows]

    async def pair_collections(self, id_a: int, id_b: int) -> None:
        await self.conn.execute(
            "UPDATE collection SET paired_id = ? WHERE id = ?", (id_b, id_a)
        )
        await self.conn.execute(
            "UPDATE collection SET paired_id = ? WHERE id = ?", (id_a, id_b)
        )
        await self.conn.commit()

    # -- collection_track -----------------------------------------------------

    async def add_track_to_collection(
        self,
        *,
        collection_id: int,
        track_mapping_id: int,
        position: int | None = None,
        added_at: str | None = None,
    ) -> CollectionTrack:
        now = _now_iso()
        cur = await self.conn.execute(
            """
            INSERT INTO collection_track (collection_id, track_mapping_id, position, added_at, synced_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (collection_id, track_mapping_id) DO UPDATE SET
                position = excluded.position,
                synced_at = excluded.synced_at,
                removed_at = NULL
            RETURNING *
            """,
            (collection_id, track_mapping_id, position, added_at, now),
        )
        row = await cur.fetchone()
        await self.conn.commit()
        return self._row_to_collection_track(row)

    async def mark_track_removed(
        self, *, collection_id: int, track_mapping_id: int
    ) -> None:
        now = _now_iso()
        await self.conn.execute(
            "UPDATE collection_track SET removed_at = ? WHERE collection_id = ? AND track_mapping_id = ?",
            (now, collection_id, track_mapping_id),
        )
        await self.conn.commit()

    async def list_collection_tracks(
        self,
        collection_id: int,
        *,
        include_removed: bool = False,
    ) -> list[CollectionTrack]:
        if include_removed:
            cur = await self.conn.execute(
                "SELECT * FROM collection_track WHERE collection_id = ? ORDER BY position",
                (collection_id,),
            )
        else:
            cur = await self.conn.execute(
                "SELECT * FROM collection_track WHERE collection_id = ? AND removed_at IS NULL ORDER BY position",
                (collection_id,),
            )
        rows = await cur.fetchall()
        return [self._row_to_collection_track(r) for r in rows]

    async def delete_removed_tracks(self, collection_id: int) -> int:
        cur = await self.conn.execute(
            "DELETE FROM collection_track WHERE collection_id = ? AND removed_at IS NOT NULL",
            (collection_id,),
        )
        await self.conn.commit()
        return cur.rowcount

    # -- unmatched ------------------------------------------------------------

    async def add_unmatched(
        self,
        *,
        source_service: str,
        source_id: str,
        artist: str,
        title: str,
    ) -> Unmatched:
        now = _now_iso()
        cur = await self.conn.execute(
            """
            INSERT INTO unmatched (source_service, source_id, artist, title, last_attempt_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (source_service, source_id) DO UPDATE SET
                attempts = unmatched.attempts + 1,
                last_attempt_at = excluded.last_attempt_at
            RETURNING *
            """,
            (source_service, source_id, artist, title, now, now),
        )
        row = await cur.fetchone()
        await self.conn.commit()
        return self._row_to_unmatched(row)

    async def resolve_unmatched(self, source_service: str, source_id: str) -> None:
        await self.conn.execute(
            "DELETE FROM unmatched WHERE source_service = ? AND source_id = ?",
            (source_service, source_id),
        )
        await self.conn.commit()

    async def list_unmatched(self, source_service: str | None = None) -> list[Unmatched]:
        if source_service:
            cur = await self.conn.execute(
                "SELECT * FROM unmatched WHERE source_service = ? ORDER BY id",
                (source_service,),
            )
        else:
            cur = await self.conn.execute("SELECT * FROM unmatched ORDER BY id")
        rows = await cur.fetchall()
        return [self._row_to_unmatched(r) for r in rows]

    # -- sync_runs ------------------------------------------------------------

    async def start_sync_run(
        self,
        *,
        direction: str,
        mode: str,
        collection_id: int | None = None,
    ) -> SyncRun:
        now = _now_iso()
        cur = await self.conn.execute(
            """
            INSERT INTO sync_runs (started_at, collection_id, direction, mode, status)
            VALUES (?, ?, ?, ?, 'running')
            RETURNING *
            """,
            (now, collection_id, direction, mode),
        )
        row = await cur.fetchone()
        await self.conn.commit()
        return self._row_to_sync_run(row)

    async def finish_sync_run(
        self,
        run_id: int,
        *,
        status: str,
        stats_json: str | None = None,
        error_message: str | None = None,
    ) -> SyncRun:
        now = _now_iso()
        cur = await self.conn.execute(
            """
            UPDATE sync_runs SET finished_at = ?, status = ?, stats_json = ?, error_message = ?
            WHERE id = ?
            RETURNING *
            """,
            (now, status, stats_json, error_message, run_id),
        )
        row = await cur.fetchone()
        await self.conn.commit()
        return self._row_to_sync_run(row)

    async def list_sync_runs(self, *, limit: int = 20) -> list[SyncRun]:
        cur = await self.conn.execute(
            "SELECT * FROM sync_runs ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        return [self._row_to_sync_run(r) for r in rows]

    # -- row → model helpers --------------------------------------------------

    @staticmethod
    def _row_to_track_mapping(row: aiosqlite.Row) -> TrackMapping:
        return TrackMapping(
            id=row["id"],
            spotify_id=row["spotify_id"],
            yandex_id=row["yandex_id"],
            artist=row["artist"],
            title=row["title"],
            match_confidence=row["match_confidence"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_collection(row: aiosqlite.Row) -> Collection:
        return Collection(
            id=row["id"],
            service=row["service"],
            collection_type=row["collection_type"],
            remote_id=row["remote_id"],
            title=row["title"],
            paired_id=row["paired_id"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_collection_track(row: aiosqlite.Row) -> CollectionTrack:
        return CollectionTrack(
            collection_id=row["collection_id"],
            track_mapping_id=row["track_mapping_id"],
            position=row["position"],
            added_at=row["added_at"],
            synced_at=row["synced_at"],
            removed_at=row["removed_at"],
        )

    @staticmethod
    def _row_to_unmatched(row: aiosqlite.Row) -> Unmatched:
        return Unmatched(
            id=row["id"],
            source_service=row["source_service"],
            source_id=row["source_id"],
            artist=row["artist"],
            title=row["title"],
            attempts=row["attempts"],
            last_attempt_at=row["last_attempt_at"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_sync_run(row: aiosqlite.Row) -> SyncRun:
        return SyncRun(
            id=row["id"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            collection_id=row["collection_id"],
            direction=row["direction"],
            mode=row["mode"],
            status=row["status"],
            stats_json=row["stats_json"],
            error_message=row["error_message"],
        )
