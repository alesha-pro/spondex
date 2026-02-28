"""Track normalization, cross-matching, and diff computation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteTrack:
    """A track as fetched from a remote service API."""

    service: str  # "spotify" | "yandex"
    remote_id: str  # platform-specific track ID
    artist: str  # raw artist name from API
    title: str  # raw track title from API
    added_at: str | None = None  # ISO timestamp when liked


@dataclass
class MatchResult:
    """Result of cross-matching two RemoteTracks."""

    spotify_track: RemoteTrack
    yandex_track: RemoteTrack
    confidence: float  # 0.0-1.0


def normalize(text: str) -> str:
    """Normalize a track title or artist name for matching.

    Steps:
    1. Unicode NFKD normalization
    2. Lowercase
    3. Remove feat./ft./featuring clauses (both in parens and inline)
    4. Remove content in parentheses/brackets (remix indicators etc)
    5. Strip punctuation except spaces
    6. Collapse whitespace
    """
    # NFKD
    text = unicodedata.normalize("NFKD", text)
    # Lowercase
    text = text.lower()
    # Remove feat/ft/featuring in parens/brackets
    text = re.sub(
        r"\s*[\(\[](feat\.?|ft\.?|featuring)\s+[^\)\]]*[\)\]]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Remove inline feat/ft/featuring and everything after
    text = re.sub(
        r"\s+(feat\.?|ft\.?|featuring)\s+.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Remove all remaining parenthetical/bracket content
    text = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", text)
    # Strip punctuation (keep letters, digits, spaces)
    text = re.sub(r"[^\w\s]", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def make_match_key(artist: str, title: str) -> str:
    """Create a normalized key from artist+title for dict-based matching."""
    return f"{normalize(artist)}|||{normalize(title)}"


def cross_match(
    spotify_tracks: list[RemoteTrack],
    yandex_tracks: list[RemoteTrack],
) -> tuple[list[MatchResult], list[RemoteTrack], list[RemoteTrack]]:
    """Cross-match two lists of tracks by normalized artist+title.

    Returns:
        (matches, unmatched_spotify, unmatched_yandex)
    """
    # Build index from yandex tracks
    ym_index: dict[str, list[RemoteTrack]] = {}
    for t in yandex_tracks:
        key = make_match_key(t.artist, t.title)
        ym_index.setdefault(key, []).append(t)

    matches: list[MatchResult] = []
    unmatched_sp: list[RemoteTrack] = []

    for sp_track in spotify_tracks:
        key = make_match_key(sp_track.artist, sp_track.title)
        candidates = ym_index.get(key)
        if candidates:
            ym_track = candidates.pop(0)
            if not candidates:
                del ym_index[key]
            matches.append(
                MatchResult(
                    spotify_track=sp_track,
                    yandex_track=ym_track,
                    confidence=1.0,
                )
            )
        else:
            unmatched_sp.append(sp_track)

    # Remaining yandex tracks
    unmatched_ym: list[RemoteTrack] = []
    for tracks in ym_index.values():
        unmatched_ym.extend(tracks)

    return matches, unmatched_sp, unmatched_ym
