"""Mood-matched music selection and alluring-but-safe scene styling."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import music_match
import post_instagram
from character.variations import QUALITY_CONSTRAINTS, VARIATIONS


def test_mood_queries_maps_scene_mood():
    queries = music_match.mood_queries("playful and alluring")
    assert "playful pop" in queries
    assert "slow r&b" in queries
    assert "sensual" in queries


def test_mood_queries_empty_for_unknown_mood():
    assert music_match.mood_queries(None) == []
    assert music_match.mood_queries("something unrecognised") == []


def test_score_track_prefers_title_matching_mood():
    hit = SimpleNamespace(title="Slow Sensual Nights", display_artist="Artist")
    miss = SimpleNamespace(title="Random Pop Song", display_artist="Other")
    assert music_match.score_track(hit, ["slow r&b", "sensual"]) > \
        music_match.score_track(miss, ["slow r&b", "sensual"])
    assert music_match.score_track(hit, []) == 0.0


def test_pick_music_track_uses_search_for_mood(monkeypatch):
    # With a mood, the picker must search the catalog rather than take a
    # random item from the global trending list.
    low = SimpleNamespace(id="1", title="Random Pop Song", display_artist="A")
    high = SimpleNamespace(id="2", title="Slow Sensual Nights", display_artist="B")
    client = MagicMock()
    client.search_music.return_value = [low, high]

    track, key = post_instagram.pick_music_track(client, mood="playful and alluring")

    client.search_music.assert_called()
    client.music_top_trends.assert_not_called()
    assert key == "2"
    assert track.title == "Slow Sensual Nights"


def test_pick_music_track_falls_back_to_trending(monkeypatch):
    client = MagicMock()
    client.search_music.return_value = []
    client.music_top_trends.return_value = {"items": []}
    assert post_instagram.pick_music_track(client, mood="alluring") == (None, None)


def test_all_variations_stay_non_explicit():
    assert len(VARIATIONS) == 12
    for variation in VARIATIONS:
        assert variation.outfit.strip()
        blob = (variation.outfit + " " + variation.pose).lower()
        assert "nude" not in blob
        assert "naked" not in blob
    assert "no nudity" in QUALITY_CONSTRAINTS
    assert "non-explicit" in QUALITY_CONSTRAINTS
