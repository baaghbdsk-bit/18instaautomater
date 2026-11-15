"""Tests for themes, layout, ASS generation and camera motion."""

import random

from generate_video import _ass_color, build_ass, layout, motion_expressions
from themes import LINE_MOODS, MUSIC_POOLS, THEME_KEYS, THEMES, pick_prompt, \
    theme_meta


def test_theme_definitions_valid():
    assert len(THEME_KEYS) >= 10
    for name, meta in THEMES.items():
        assert meta["mood"] in LINE_MOODS, name
        assert meta["music"] in MUSIC_POOLS, name
        assert len(meta["prompts"]) >= 3, name
        for p in meta["prompts"]:
            assert len(p) > 60, f"{name}: prompt too short"
            assert "9:16" in p, f"{name}: prompts must ask for 9:16"


def test_theme_meta_fallback():
    assert theme_meta("no_such_theme")["theme"] == "night_neon"
    assert theme_meta("fitness")["theme"] == "fitness"


def test_pick_prompt_uses_unused_first():
    unused = {THEMES["fitness"]["prompts"][0]}
    p = pick_prompt("fitness", unused)
    assert p not in unused
    # with everything used, it still returns something
    assert pick_prompt("fitness", set(THEMES["fitness"]["prompts"]))


def test_layout_stays_within_four_lines():
    long_line = ("You were supposed to keep scrolling past me but here you "
                 "are still watching everything")
    q = layout(long_line)
    assert len(q["lines"]) <= 5                     # 4 normally, 5 at fallback
    assert q["size"] in (116, 108, 100, 92, 84, 76, 68)
    joined = " ".join(q["lines"])
    assert "scrolling" in joined                    # no words dropped


def test_layout_short_line_gets_big_font():
    q = layout("Miss me yet, honestly")
    assert q["size"] >= 100


def test_ass_color_conversion():
    assert _ass_color("0xFFFFC61A") == "&H001AC6FF"   # opaque yellow
    assert _ass_color("0x80FF0000") == "&H7F0000FF"   # 50% red (&H7F BBGGRR)


def test_build_ass_structure():
    q = layout("Bet you can't look away from this one")
    ass = build_ass(q, 1080, 1920, 12.0, "upper", "@xene.ai")
    assert "PlayResX: 1080" in ass
    assert "PlayResY: 1920" in ass
    assert "Style: Quote,Anton," in ass
    assert "Style: Mark,Archivo Black,38," in ass
    assert "@xene.ai" in ass
    assert ass.count("Dialogue:") == len(q["lines"]) + 1   # lines + watermark
    # events reference the Quote style, not an unknown one
    assert ",Quote,,0,0,0,," in ass


def test_motion_expressions_are_wellformed():
    for m in ["push_center", "push_up", "push_down", "drift_left", "drift_right"]:
        expr = motion_expressions(m, frames=360)
        assert "undefined" not in str(expr)
        assert "NaN" not in str(expr)
        assert expr["z"].startswith("min(1+")
