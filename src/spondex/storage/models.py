"""Pydantic models for the Spondex storage layer."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ServiceName = Literal["spotify", "yandex"]
CollectionType = Literal["liked", "playlist", "album"]
SyncDirection = Literal["spotify_to_yandex", "yandex_to_spotify", "bidirectional"]
SyncMode = Literal["full", "incremental"]
SyncStatus = Literal["running", "completed", "failed", "cancelled"]


class TrackMapping(BaseModel):
    """Cross-platform track mapping."""

    id: int | None = None
    spotify_id: str | None = None
    yandex_id: str | None = None
    artist: str
    title: str
    match_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Collection(BaseModel):
    """A container of tracks: liked songs, playlist, or album (v2)."""

    id: int | None = None
    service: ServiceName
    collection_type: CollectionType
    remote_id: str | None = None
    title: str
    paired_id: int | None = None
    created_at: datetime | None = None


class CollectionTrack(BaseModel):
    """Association between a collection and a track mapping."""

    collection_id: int
    track_mapping_id: int
    position: int | None = None
    added_at: datetime | None = None
    synced_at: datetime | None = None
    removed_at: datetime | None = None


class Unmatched(BaseModel):
    """A track that could not be found on the target platform."""

    id: int | None = None
    source_service: ServiceName
    source_id: str
    artist: str
    title: str
    attempts: int = 1
    last_attempt_at: datetime | None = None
    created_at: datetime | None = None


class SyncRun(BaseModel):
    """Record of a single synchronisation run."""

    id: int | None = None
    started_at: datetime
    finished_at: datetime | None = None
    collection_id: int | None = None
    direction: SyncDirection
    mode: SyncMode
    status: SyncStatus
    stats_json: str | None = None
    error_message: str | None = None
