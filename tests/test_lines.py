"""Tests for line normalisation, dedupe and filters (no network)."""

import lines


def test_normalise():
    assert lines.normalise("Hello,  World!!") == "hello world"
    assert lines.normalise("it's a TEST") == "it s a test"
    assert lines.normalise("") == ""


def test_similar_jaccard():
    a = "Bet you can't look away from this one"
    b = "Bet you really can't look away from this one"
    c = "Late night thoughts are quiet tonight"
    assert lines.similar(a, b) is True
    assert lines.similar(a, c) is False


def test_accept_line_filters():
    pool = ["Bet you can't look away from this one"]
    # too short
    assert lines.accept_line("Hi there", pool) is None
    # emoji stripped -> too short
    assert lines.accept_line("Hey 🔥", pool) is None
    # hashtag rejected
    assert lines.accept_line("You will not scroll past this #tag", pool) is None
    # cliché rejected
    assert lines.accept_line("Never give up on your dreams tonight", pool) is None
    # near-duplicate of pool rejected
    assert lines.accept_line("Bet you can't look away from this one ok", pool) \
        is None
    # good line passes
    good = lines.accept_line("You were supposed to keep scrolling past me", pool)
    assert good is not None
    assert not any(ord(c) > 0x24F for c in good)


def test_seed_bank_quality():
    seen = set()
    for mood, pool in lines.SEED.items():
        assert len(pool) >= 25, f"{mood} pool too small"
        for ln in pool:
            assert 18 <= len(ln) <= 118, f"bad length for {ln!r}: {len(ln)}"
            assert ln not in seen, f"duplicate seed: {ln!r}"
            seen.add(ln)
            assert not lines.is_cliche(ln), f"cliché in seed: {ln!r}"
            assert lines.normalise(ln)
        assert mood in lines.CTAS and mood in lines.HASHTAGS
        assert len(lines.CTAS[mood]) >= 3
        assert len(lines.HASHTAGS[mood]) >= 8


def test_clean_hashtags():
    tags = lines.clean_hashtags(
        ["#Reels", "#reels", "#bad tag", "#ok_tag", "#a", "#x" * 30])
    assert tags == ["#reels", "#ok_tag"]


def test_first_line():
    assert lines.first_line("  Hello world \n second ") == "hello world"
    assert lines.first_line("") == ""


def test_strip_emoji():
    assert lines.strip_emoji("Hot 🔥 and 💋 ready") == "Hot  and  ready"
