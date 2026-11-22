"""Music identity: SLOWBURN only, resolved live, 48h persistent rotation."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import db
import music_match
import post_instagram
from character.variations import QUALITY_CONSTRAINTS, VARIATIONS


def test_all_curated_tracks_are_slowburn():
    assert len(music_match.CURATED_TRACKS) == 10
    for item in music_match.CURATED_TRACKS.values():
        assert item["artist"] == "SLOWBURN"


def test_no_orgavsm_tracks_remain():
    assert music_match.ORGAVSM_KEYS == ()
    for item in music_match.curated_for_mood("dreamy and free"):
        assert item["artist"] == "SLOWBURN"


def test_find_track_uses_search_music_only():
    item = music_match.CURATED_TRACKS["crave_you"]
    fake = SimpleNamespace(id=item["track_id"], title="Crave You",
                           display_artist="SLOWBURN",
                           progressive_download_url="http://audio")
    client = MagicMock()
    client.search_music.return_value = [fake]
    assert music_match.find_curated_track(client, item) is fake
    client.search_music.assert_any_call("slowburn")


def test_cooldown_is_persisted_in_db(monkeypatch):
    key = "crave_you"
    monkeypatch.setattr(music_match.time, "time", lambda: 1000.0)
    db.set_state(f"music_last_used:{key}", "500")
    assert music_match._cooldown_expired(key) is False  # 500s < 48h
    db.set_state(f"music_last_used:{key}", "-172000")
    assert music_match._cooldown_expired(key) is True


def test_pick_logs_audio_id_and_rotates():
    for key in music_match.SLOWBURN_KEYS:
        db.set_state(f"music_last_used:{key}", "0")
    first = music_match.CURATED_TRACKS["crave_you"]
    second = music_match.CURATED_TRACKS["torture_me_gently"]
    a = SimpleNamespace(id=first["track_id"], title="Crave You",
                        display_artist="SLOWBURN",
                        progressive_download_url="http://audio")
    b = SimpleNamespace(id=second["track_id"], title="Torture Me Gently",
                        display_artist="SLOWBURN",
                        progressive_download_url="http://audio")
    client = MagicMock()
    client.search_music.return_value = [a, b]

    track, key = post_instagram.pick_music_track(
        client, used_keys=[first["track_id"]], mood="flirty")
    assert key == second["track_id"]
    assert track.title == "Torture Me Gently"
    client.music_top_trends.assert_not_called()


def test_pick_returns_none_when_catalog_unavailable(monkeypatch):
    monkeypatch.setattr(music_match, "_trending_catalog", lambda cl: [])
    client = MagicMock()
    client.search_music.return_value = []
    assert post_instagram.pick_music_track(client, mood="flirty") == (None, None)


def test_trending_catalog_fallback_when_search_broken(monkeypatch):
    item = music_match.CURATED_TRACKS["crave_you"]
    fake = SimpleNamespace(id=item["track_id"], title="Crave You",
                           display_artist="SLOWBURN",
                           progressive_download_url="http://audio")
    monkeypatch.setattr(music_match, "_trending_catalog", lambda cl: [fake])
    client = MagicMock()
    client.search_music.side_effect = AttributeError("'NoneType' object has no attribute 'get'")
    assert music_match.find_curated_track(client, item) is fake


def test_styling_guardrails_intact():
    assert len(VARIATIONS) == 12
    for variation in VARIATIONS:
        blob = (variation.outfit + " " + variation.pose).lower()
        assert "nude" not in blob and "naked" not in blob
    assert "non-nude" in QUALITY_CONSTRAINTS
