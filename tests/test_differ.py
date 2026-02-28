"""Tests for the sync differ module."""

from __future__ import annotations

from spondex.sync.differ import (
    RemoteTrack,
    cross_match,
    make_match_key,
    normalize,
)


# -- normalize tests --


def test_normalize_lowercase():
    assert normalize("Hello World") == "hello world"


def test_normalize_strips_feat_in_parens():
    assert normalize("Song (feat. Artist)") == "song"


def test_normalize_strips_ft_in_brackets():
    assert normalize("Song [ft. Artist]") == "song"


def test_normalize_strips_featuring_inline():
    assert normalize("Song featuring Another Artist") == "song"


def test_normalize_strips_parenthetical_content():
    assert normalize("Song (Remix)") == "song"
    assert normalize("Song [Deluxe Edition]") == "song"


def test_normalize_unicode_accents():
    # NFKD decomposes accented chars
    result = normalize("Beyonce\u0301")
    assert "beyonce" in result


def test_normalize_collapses_whitespace():
    assert normalize("  hello   world  ") == "hello world"


def test_normalize_strips_punctuation():
    assert normalize("rock & roll!") == "rock roll"


def test_normalize_complex():
    assert normalize("Lose Yourself (feat. Eminem) [Remix]") == "lose yourself"


# -- make_match_key tests --


def test_match_key_deterministic():
    key1 = make_match_key("Artist", "Title")
    key2 = make_match_key("Artist", "Title")
    assert key1 == key2


def test_match_key_normalized():
    key1 = make_match_key("Artist", "Song (feat. Someone)")
    key2 = make_match_key("artist", "Song")
    assert key1 == key2


# -- cross_match tests --


def _sp(remote_id: str, artist: str, title: str) -> RemoteTrack:
    return RemoteTrack(
        service="spotify", remote_id=remote_id, artist=artist, title=title
    )


def _ym(remote_id: str, artist: str, title: str) -> RemoteTrack:
    return RemoteTrack(
        service="yandex", remote_id=remote_id, artist=artist, title=title
    )


def test_cross_match_exact():
    sp = [_sp("s1", "Radiohead", "Creep")]
    ym = [_ym("y1", "Radiohead", "Creep")]
    matches, unmatched_sp, unmatched_ym = cross_match(sp, ym)
    assert len(matches) == 1
    assert matches[0].spotify_track.remote_id == "s1"
    assert matches[0].yandex_track.remote_id == "y1"
    assert matches[0].confidence == 1.0
    assert unmatched_sp == []
    assert unmatched_ym == []


def test_cross_match_with_normalization():
    sp = [_sp("s1", "Radiohead", "Creep (feat. Someone)")]
    ym = [_ym("y1", "radiohead", "Creep")]
    matches, unmatched_sp, unmatched_ym = cross_match(sp, ym)
    assert len(matches) == 1


def test_cross_match_no_matches():
    sp = [_sp("s1", "Artist A", "Song A")]
    ym = [_ym("y1", "Artist B", "Song B")]
    matches, unmatched_sp, unmatched_ym = cross_match(sp, ym)
    assert len(matches) == 0
    assert len(unmatched_sp) == 1
    assert len(unmatched_ym) == 1


def test_cross_match_partial():
    sp = [_sp("s1", "A", "X"), _sp("s2", "B", "Y")]
    ym = [_ym("y1", "A", "X"), _ym("y2", "C", "Z")]
    matches, unmatched_sp, unmatched_ym = cross_match(sp, ym)
    assert len(matches) == 1
    assert len(unmatched_sp) == 1
    assert unmatched_sp[0].remote_id == "s2"
    assert len(unmatched_ym) == 1
    assert unmatched_ym[0].remote_id == "y2"


def test_cross_match_empty_lists():
    matches, unmatched_sp, unmatched_ym = cross_match([], [])
    assert matches == []
    assert unmatched_sp == []
    assert unmatched_ym == []


def test_cross_match_one_empty():
    sp = [_sp("s1", "A", "X")]
    matches, unmatched_sp, unmatched_ym = cross_match(sp, [])
    assert len(matches) == 0
    assert len(unmatched_sp) == 1
    assert unmatched_ym == []
