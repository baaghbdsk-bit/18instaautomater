"""Music identity: SLOWBURN only, no generic trending fallback."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import music_match
import post_instagram
from character.variations import QUALITY_CONSTRAINTS, VARIATIONS


def test_every_curated_track_is_approved():
    assert len(music_match.SLOWBURN_KEYS) == 10
    assert len(music_match.ORGAVSM_KEYS) == 5
    for item in music_match.CURATED_TRACKS.values():
        assert item["artist"] in music_match.APPROVED_ARTISTS
        assert item["track_id"].isdigit()


def test_mood_maps_only_to_approved_artists_and_prefers_slowburn():
    for mood in ("playful and alluring", "dreamy and free", "bold and electric",
                 "high fashion and commanding", ""):
        items = music_match.curated_for_mood(mood)
        assert items
        assert all(i["artist"] in music_match.APPROVED_ARTISTS for i in items)
        assert len({i["track_id"] for i in items}) == len(items)
        # SLOWBURN always comes before ORGAVSM in the rotation.
        first_orgavsm = next(
            (n for n, i in enumerate(items)
             if i["artist"] != "SLOWBURN"), len(items))
        assert all(i["artist"] == "SLOWBURN"
                   for i in items[:first_orgavsm])


def test_find_curated_track_matches_exact_id():
    wanted = music_match.CURATED_TRACKS["crave_you"]
    right = SimpleNamespace(id=wanted["track_id"], title="Crave You")
    wrong = SimpleNamespace(id="1", title="Crave You")
    client = MagicMock()
    client.search_music.return_value = [wrong, right]
    assert music_match.find_curated_track(client, wanted) is right


def test_pick_music_track_never_uses_trending(monkeypatch):
    wanted = music_match.CURATED_TRACKS["crave_you"]
    fake_track = SimpleNamespace(id=wanted["track_id"], title="Crave You",
                                 display_artist="SLOWBURN")
    client = MagicMock()
    client.search_music.return_value = [fake_track]

    track, key = post_instagram.pick_music_track(client, mood="playful and alluring")

    client.music_top_trends.assert_not_called()
    assert key == wanted["track_id"]
    assert track.title == "Crave You"


def test_pick_music_track_skips_used_tracks():
    first = music_match.CURATED_TRACKS["tease_me"]
    second = music_match.CURATED_TRACKS["crave_you"]
    a = SimpleNamespace(id=first["track_id"], title="Tease Me",
                        display_artist="SLOWBURN")
    b = SimpleNamespace(id=second["track_id"], title="Crave You",
                        display_artist="SLOWBURN")
    client = MagicMock()
    client.search_music.return_value = [a, b]

    track, key = post_instagram.pick_music_track(
        client, used_keys=[first["track_id"]], mood="flirty")
    assert key == second["track_id"]


def test_pick_music_track_fails_soft_without_catalog():
    client = MagicMock()
    client.search_music.return_value = []
    assert post_instagram.pick_music_track(client, mood="flirty") == (None, None)


def test_track_from_metadata_uses_right_artist_search():
    client = MagicMock()
    client.search_music.return_value = []
    music_match.track_from_metadata(
        client, {"track_id": "876032214956457", "title": "Crave You",
                 "artist": "SLOWBURN"})
    client.search_music.assert_called_with("slowburn")

    client.search_music.reset_mock()
    music_match.track_from_metadata(
        client, {"track_id": "3715502165250716", "title": "Naughty",
                 "artist": "ORGAVSM"})
    client.search_music.assert_called_with("orgavsm")


def test_all_variations_stay_non_explicit():
    assert len(VARIATIONS) == 12
    for variation in VARIATIONS:
        assert variation.outfit.strip()
        blob = (variation.outfit + " " + variation.pose).lower()
        assert "nude" not in blob
        assert "naked" not in blob
    assert "non-nude" in QUALITY_CONSTRAINTS
    assert "no explicit sexual activity" in QUALITY_CONSTRAINTS
