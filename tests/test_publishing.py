"""Tests for the static-image publishing helpers (no network, no credentials).

The instagrapi client is always a MagicMock — nothing here can post, log in,
or touch a real session file.
"""

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from instagrapi.exceptions import ChallengeRequired, LoginRequired

import post_instagram


CAPTION = "A quiet line that is long enough to dedupe\n#quotes"


@contextmanager
def harness(duplicate=None, username="user"):
    """Patch the network-ish collaborators around upload_photo_post."""
    with patch.object(post_instagram, "ensure_session",
                      return_value=username) as ensure, \
         patch.object(post_instagram, "find_duplicate",
                      return_value=duplicate) as dup, \
         patch.object(post_instagram.time, "sleep") as sleep:
        yield SimpleNamespace(ensure=ensure, dup=dup, sleep=sleep)


@pytest.fixture
def image(tmp_path):
    """A real, non-empty image placeholder on disk (contents are irrelevant)."""
    p = tmp_path / "quote.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    return p


# ---------------------------------------------------------------------------
# upload_photo_post
# ---------------------------------------------------------------------------
def test_upload_photo_success_returns_ok_pk_code(image):
    cl = MagicMock()
    cl.photo_upload.return_value = MagicMock(pk=4242, code="AbC123")

    with harness():
        res = post_instagram.upload_photo_post(
            cl, "user", image, CAPTION, attempts=3)

    assert res["ok"] is True
    assert res["pk"] == "4242"
    assert res["code"] == "AbC123"
    assert res["recovered"] is False
    assert res["error"] is None
    assert res["attempts"] == 1
    assert cl.photo_upload.call_count == 1


def test_photo_upload_called_with_exact_path_and_caption(tmp_path):
    cl = MagicMock()
    cl.photo_upload.return_value = MagicMock(pk=1, code="X")
    spaced = tmp_path / "my quote post.png"      # exact path, spaces included
    spaced.write_bytes(b"x" * 64)
    caption = "First line of the post\nsecond line\n#tag"

    with harness():
        post_instagram.upload_photo_post(cl, "user", spaced, caption)

    cl.photo_upload.assert_called_once_with(str(spaced), caption=caption)


def test_empty_and_missing_image_fail_without_upload(tmp_path):
    cl = MagicMock()
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    missing = tmp_path / "does-not-exist.png"

    with harness():
        r_empty = post_instagram.upload_photo_post(
            cl, "user", empty, CAPTION)
        r_missing = post_instagram.upload_photo_post(
            cl, "user", missing, CAPTION)

    assert r_empty["ok"] is False and r_missing["ok"] is False
    assert "missing or empty" in r_empty["error"]
    assert "missing or empty" in r_missing["error"]
    assert r_empty["attempts"] == 0 and r_missing["attempts"] == 0
    cl.photo_upload.assert_not_called()


def test_challenge_required_fails_fast_without_retry(image):
    cl = MagicMock()
    cl.photo_upload.side_effect = ChallengeRequired("challenge required")

    with harness() as m:
        res = post_instagram.upload_photo_post(
            cl, "user", image, CAPTION, attempts=3)

    assert res["ok"] is False
    assert "ChallengeRequired" in res["error"]
    assert res["attempts"] == 1
    assert cl.photo_upload.call_count == 1          # no retry
    m.sleep.assert_not_called()
    m.dup.assert_not_called()                       # no double-post probe


def test_network_error_then_success_on_second_attempt(image):
    cl = MagicMock()
    cl.photo_upload.side_effect = [
        TimeoutError("timed out"),
        MagicMock(pk="777", code="SECOND"),
    ]

    with harness() as m:
        res = post_instagram.upload_photo_post(
            cl, "user", image, CAPTION, attempts=3)

    assert res["ok"] is True
    assert res["pk"] == "777"
    assert res["code"] == "SECOND"
    assert res["attempts"] == 2
    assert cl.photo_upload.call_count == 2
    m.sleep.assert_called_once_with(8)               # 8 * (0 + 1)
    m.dup.assert_called_once_with(cl, "user", CAPTION, lookback=10)


def test_failed_upload_recovers_when_post_is_already_live(image):
    cl = MagicMock()
    cl.photo_upload.side_effect = [
        ConnectionError("connection reset"),
        MagicMock(pk="never-used", code="NO"),
    ]

    with harness(duplicate="999") as m:
        res = post_instagram.upload_photo_post(
            cl, "user", image, CAPTION, attempts=3)

    assert res["ok"] is True
    assert res["recovered"] is True
    assert res["pk"] == "999"
    assert res["attempts"] == 1
    assert cl.photo_upload.call_count == 1            # no double-post
    m.dup.assert_called_once_with(cl, "user", CAPTION, lookback=10)


def test_final_failure_returns_last_error(image):
    cl = MagicMock()
    cl.photo_upload.side_effect = TimeoutError("still down")

    with harness() as m:
        res = post_instagram.upload_photo_post(
            cl, "user", image, CAPTION, attempts=2)

    assert res["ok"] is False
    assert "TimeoutError" in res["error"]
    assert "still down" in res["error"]
    assert res["attempts"] == 2
    assert cl.photo_upload.call_count == 2
    m.dup.assert_called_once()                        # probed after first fail


# ---------------------------------------------------------------------------
# ensure_session
# ---------------------------------------------------------------------------
def test_ensure_session_login_required_is_clear_and_leaks_nothing():
    cl = MagicMock()
    cl.username = "alice"
    # Pretend the exception body carries a cookie — it must not surface.
    cl.account_info.side_effect = LoginRequired("cookie=SUPER_SECRET_TOKEN")

    with pytest.raises(RuntimeError) as excinfo:
        post_instagram.ensure_session(cl)

    msg = str(excinfo.value)
    assert "expired" in msg.lower()
    assert "sessions/alice.json" in msg
    assert "re-login" in msg.lower()
    assert "SUPER_SECRET_TOKEN" not in msg
    assert "cookie" not in msg.lower()
    cl.account_info.assert_called_once_with()


def test_ensure_session_returns_username():
    cl = MagicMock()
    cl.account_info.return_value = MagicMock(username="bob")
    assert post_instagram.ensure_session(cl) == "bob"


def test_ensure_session_other_exception_has_context():
    cl = MagicMock()
    cl.account_info.side_effect = OSError("socket closed")

    with pytest.raises(RuntimeError, match="OSError") as excinfo:
        post_instagram.ensure_session(cl)
    assert isinstance(excinfo.value.__cause__, OSError)


# ---------------------------------------------------------------------------
# session_status
# ---------------------------------------------------------------------------
def test_session_status_reports_cached_path_without_reading_contents(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    account = {"name": "a1", "username": "alice"}

    with patch.object(post_instagram, "SESSIONS_DIR", sessions):
        before = post_instagram.session_status(account)
        assert before["cached"] is False
        assert before["size"] == 0

        sess_file = sessions / "alice.json"
        sess_file.write_text('{"cookies": [{"value": "secret"}]}')
        expected_size = sess_file.stat().st_size

        # Reading the file at all is a failure — only stat() is allowed.
        with patch.object(Path, "read_text",
                          side_effect=AssertionError("session contents read!")), \
             patch.object(Path, "read_bytes",
                          side_effect=AssertionError("session contents read!")):
            after = post_instagram.session_status(account)

    assert after["username"] == "alice"
    assert after["cached"] is True
    assert after["size"] == expected_size
    assert after["path"] == str(sess_file)


# ---------------------------------------------------------------------------
# preflight_or_login
# ---------------------------------------------------------------------------
def test_preflight_or_login_reuses_existing_client():
    existing = MagicMock()
    clients = {"a1": existing}

    with patch.object(post_instagram, "login_account") as login:
        got = post_instagram.preflight_or_login({"name": "a1"}, clients)

    assert got is existing
    login.assert_not_called()


def test_preflight_or_login_logs_in_only_when_missing():
    fresh = MagicMock()
    clients = {}
    account = {"name": "a1", "username": "alice", "password": "pw"}

    with patch.object(post_instagram, "login_account",
                      return_value=fresh) as login:
        got = post_instagram.preflight_or_login(account, clients)

    assert got is fresh
    assert clients["a1"] is fresh
    login.assert_called_once_with(account)


def test_logout_all_keeps_sessions_reusable_by_default():
    client = MagicMock()
    clients = {"a1": client}
    post_instagram.logout_all(clients)
    client.logout.assert_not_called()
    assert clients == {}


def test_logout_all_can_explicitly_invalidate():
    client = MagicMock()
    clients = {"a1": client}
    post_instagram.logout_all(clients, invalidate=True)
    client.logout.assert_called_once_with()
    assert clients == {}


_TRACK = {
    "id": "12345",
    "title": "Trending Sound",
    "subtitle": "Trending Sound",
    "display_artist": "Some Artist",
    "audio_cluster_id": "999",
    "music_canonical_id": "canon-1",
    "highlight_start_times_in_ms": [0],
    "is_explicit": False,
    "dash_manifest": "<MPD><BaseURL>https://example.invalid/a.m4a</BaseURL></MPD>",
    "has_lyrics": False,
    "audio_asset_id": "777",
    "duration_in_ms": 30000,
    "allows_saving": True,
    "territory_validity_periods": {},
}


def _write_image(path):
    from PIL import Image
    Image.new("RGB", (64, 64), (20, 20, 20)).save(path)
    return path


def test_upload_photo_post_uses_music_api_when_track_given(tmp_path):
    image = _write_image(tmp_path / "post.jpg")
    track = MagicMock()
    track.title = "Trending Sound"
    client = MagicMock()
    client.account_info.return_value = MagicMock(username="alice")
    client.photo_upload_with_music.return_value = MagicMock(pk=1, code="abc")

    result = post_instagram.upload_photo_post(client, "alice", image, "cap",
                                              track=track)

    assert result["ok"] is True
    client.photo_upload.assert_not_called()
    client.photo_upload_with_music.assert_called_once()
    kwargs = client.photo_upload_with_music.call_args.kwargs
    assert kwargs["caption"] == "cap"
    assert kwargs["track"] is track


def test_find_trending_tracks_parses_catalog_response():
    client = MagicMock()
    client.music_top_trends.return_value = {
        "items": [{"track": dict(_TRACK)}]
    }
    tracks = post_instagram.find_trending_tracks(client, source="trending")
    assert len(tracks) == 1
    assert tracks[0].title == "Trending Sound"
    assert tracks[0].display_artist == "Some Artist"


def test_find_trending_tracks_falls_back_to_trending_endpoint():
    client = MagicMock()
    client.music_top_trends.return_value = {}
    client.music_trending.return_value = {"tracks": [dict(_TRACK)]}
    tracks = post_instagram.find_trending_tracks(client, source="trending")
    assert len(tracks) == 1


def test_find_trending_tracks_off_returns_empty():
    assert post_instagram.find_trending_tracks(MagicMock(), source="off") == []


def test_pick_music_track_prefers_unused():
    client = MagicMock()
    first = dict(_TRACK)
    first["id"], first["title"] = "a", "First"
    second = dict(_TRACK)
    second["id"], second["title"] = "b", "Second"
    client.music_top_trends.return_value = {
        "items": [{"track": first}, {"track": second}]
    }
    track, key = post_instagram.pick_music_track(client, used_keys=["a"])
    assert key == "b"
    assert track.title == "Second"


def test_upload_reel_with_music_uses_music_api(tmp_path):
    video = tmp_path / "reel.mp4"
    video.write_bytes(b"0" * 1024)
    track = MagicMock()
    track.title = "Trending"
    client = MagicMock()
    client.account_info.return_value = MagicMock(username="alice")
    client.clip_upload_with_music.return_value = MagicMock(pk=55, code="xyz")

    result = post_instagram.upload_reel_with_music(
        client, "alice", video, "cap", track=track)

    assert result["ok"] is True
    assert result["pk"] == "55"
    client.clip_upload.assert_not_called()
    kwargs = client.clip_upload_with_music.call_args.kwargs
    assert kwargs["caption"] == "cap"
    assert kwargs["track"] is track


def test_upload_reel_with_music_reports_challenge_without_retry(tmp_path):
    video = tmp_path / "reel.mp4"
    video.write_bytes(b"0" * 1024)
    client = MagicMock()
    client.account_info.return_value = MagicMock(username="alice")
    client.clip_upload_with_music.side_effect = ChallengeRequired("challenge")

    result = post_instagram.upload_reel_with_music(
        client, "alice", video, "cap", track=MagicMock(), attempts=3)

    assert result["ok"] is False
    assert client.clip_upload_with_music.call_count == 1
