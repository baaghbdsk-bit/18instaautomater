"""
tests/test_youtube.py — Unit tests for YouTube Shorts upload module.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import post_youtube


def test_is_configured_false(monkeypatch, tmp_path):
    monkeypatch.setattr(post_youtube, "TOKEN_FILE", tmp_path / "nonexistent.json")
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_REFRESH_TOKEN", raising=False)
    assert not post_youtube.is_configured()


def test_is_configured_true_from_env(monkeypatch, tmp_path):
    monkeypatch.setattr(post_youtube, "TOKEN_FILE", tmp_path / "nonexistent.json")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "dummy_id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "dummy_secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "dummy_refresh")
    assert post_youtube.is_configured()


def test_upload_short_missing_file():
    res = post_youtube.upload_short("nonexistent_video.mp4", "Test title")
    assert not res["ok"]
    assert "missing or empty" in res["error"]


def test_upload_short_title_and_description_formatting(tmp_path):
    fake_video = tmp_path / "sample.mp4"
    fake_video.write_bytes(b"dummy video content")

    mock_service = MagicMock()
    mock_request = MagicMock()
    mock_request.next_chunk.return_value = (None, {"id": "yt_short_123"})
    mock_service.videos().insert.return_value = mock_request

    with patch("post_youtube.get_youtube_service", return_value=mock_service):
        res = post_youtube.upload_short(
            video_path=fake_video,
            title="My Awesome Video",
            description="Check out this quote",
        )

    assert res["ok"]
    assert res["id"] == "yt_short_123"
    assert res["url"] == "https://youtube.com/shorts/yt_short_123"

    call_kwargs = mock_service.videos().insert.call_args[1]
    body = call_kwargs["body"]
    assert "#shorts" in body["snippet"]["title"].lower()
    assert "#shorts" in body["snippet"]["description"].lower()
    assert body["status"]["privacyStatus"] == "public"
