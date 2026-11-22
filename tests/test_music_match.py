"""Music identity: ORGAVSM only, resolved live, 48h persistent rotation."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import db
import music_match
import post_instagram
from character.variations import QUALITY_CONSTRAINTS, VARIATIONS


def test_all_curated_tracks_are_orgavsm():
    assert len(music_match.CURATED_TRACKS) == 5
    for item in music_match.CURATED_TRACKS.values():
        assert "ORGAVSM" in item["artist"]
        assert item["query"] == "orgavsm"


def test_no_slowburn_tracks_remain():
    assert music_match.SLOWBURN_KEYS == ()
    for item in music_match.curated_for_mood("dreamy and free"):
        assert "ORGAVSM" in item["artist"]


def test_find_track_uses_search_music_only():
    item = music_match.CURATED_TRACKS["naughty"]
    fake = SimpleNamespace(id=item["track_id"], title="Naughty",
                           display_artist="ORGAVSM",
                           progressive_download_url="http://audio")
    client = MagicMock()
    client.search_music.return_value = [fake]
    assert music_match.find_curated_track(client, item) is fake
    assert any(c.args[0] == "orgavsm" for c in client.search_music.call_args_list)


def test_cooldown_is_persisted_in_db(monkeypatch):
    key = "naughty"
    monkeypatch.setattr(music_match.time, "time", lambda: 1000.0)
    db.set_state(f"orgavsm_last_used:{key}", "500")
    assert music_match._cooldown_expired(key) is False  # 500s < 48h
    db.set_state(f"orgavsm_last_used:{key}", "-172000")
    assert music_match._cooldown_expired(key) is True


def test_pick_logs_audio_id_and_rotates():
    # Persistent cooldown state must not leak between CI runs/tests.
    for key in music_match.ORGAVSM_KEYS:
        db.set_state(f"orgavsm_last_used:{key}", "0")
    first = music_match.CURATED_TRACKS["touch_my_body"]
    second = music_match.CURATED_TRACKS["naughty"]
    a = SimpleNamespace(id=first["track_id"], title="Touch my body",
                        display_artist="ORGAVSM",
                        progressive_download_url="http://audio")
    b = SimpleNamespace(id=second["track_id"], title="Naughty",
                        display_artist="ORGAVSM",
                        progressive_download_url="http://audio")
    client = MagicMock()
    client.search_music.return_value = [a, b]

    track, key = post_instagram.pick_music_track(
        client, used_keys=[first["track_id"]], mood="flirty")
    assert key == second["track_id"]
    assert track.title == "Naughty"
    client.music_top_trends.assert_not_called()


def test_pick_returns_none_when_catalog_unavailable():
    client = MagicMock()
    client.search_music.return_value = []
    assert post_instagram.pick_music_track(client, mood="flirty") == (None, None)


def test_styling_guardrails_intact():
    assert len(VARIATIONS) == 12
    for variation in VARIATIONS:
        blob = (variation.outfit + " " + variation.pose).lower()
        assert "nude" not in blob and "naked" not in blob
    assert "non-nude" in QUALITY_CONSTRAINTS
