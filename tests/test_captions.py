"""Caption sanitising: a broken byte from the LLM must not reach Instagram."""

import lines


def test_build_caption_repairs_replacement_character(monkeypatch):
    # The LLM branch only runs when a key is configured (CI has one).
    monkeypatch.setattr(lines, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(
        lines, "chat_json",
        lambda *a, **k: {"hook": "What\ufffds on your mind?", "hashtags": ["#a"]},
    )
    caption = lines.build_caption("glamour", "flirty", "Test line.", credit="")
    assert "\ufffd" not in caption
    assert "What's on your mind?" in caption


def test_build_caption_falls_back_when_llm_is_offline(monkeypatch):
    monkeypatch.setattr(lines, "chat_json", lambda *a, **k: None)
    caption = lines.build_caption("glamour", "flirty", "Test line.", credit="")
    assert caption.startswith("Test line.")
    assert "#" in caption
