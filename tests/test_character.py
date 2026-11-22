"""Tests for the single-character identity and variation engine."""

import json
import random
from dataclasses import fields

from character.consistency import (
    IDENTITY_MARKERS,
    assert_identity_preserved,
    build_consistency,
    consistency_metadata,
)
from character.profile import DEFAULT_NEGATIVE_PROMPT, MASTER_PROFILE
from character.variations import (
    ALLURE_V2,
    DIMENSIONS,
    NAUGHTY_ACTIONS,
    POSE_ENFORCEMENT,
    QUALITY_CONSTRAINTS,
    VARIATIONS,
    build_prompt,
    get_variation,
    select_variation,
    variation_keys,
)
from config import PERCHANCE_NEGATIVE


def test_identity_prompt_stability():
    assert MASTER_PROFILE.identity_prompt() == MASTER_PROFILE.fixed_identity
    assert MASTER_PROFILE.identity_prompt() == MASTER_PROFILE.identity_prompt()
    assert "South Asian Indian" in MASTER_PROFILE.identity_prompt()
    assert "DRY MATTE real human texture visible pores" in MASTER_PROFILE.identity_prompt()
    assert "SAME FACE EVERY IMAGE" in MASTER_PROFILE.identity_prompt()
    assert "small mole below left lip" in MASTER_PROFILE.identity_prompt()
    assert "BIG full heavy DD bust" in MASTER_PROFILE.identity_prompt()


def test_all_variations_have_required_dimension_keys():
    field_names = tuple(f.name for f in fields(VARIATIONS[0]))
    assert set(field_names) == set(DIMENSIONS)
    for variation in VARIATIONS:
        assert set(v.name for v in fields(variation)) == set(DIMENSIONS)
        assert all(hasattr(variation, dim) for dim in DIMENSIONS)


def test_variation_keys_and_fallback():
    keys = variation_keys()
    assert len(keys) >= 12
    assert len(set(keys)) == len(keys)
    assert get_variation(keys[0]).key == keys[0]
    assert get_variation("does_not_exist").key == keys[0]  # documented fallback


def test_every_variation_is_coherent_nonempty():
    assert len(VARIATIONS) >= 12
    for variation in VARIATIONS:
        for dim in DIMENSIONS:
            value = getattr(variation, dim)
            assert isinstance(value, str) and value.strip(), (
                f"{variation.key}: {dim} must be a non-empty string"
            )


def test_build_prompt_identity_first_and_markers_preserved():
    prompt = build_prompt(MASTER_PROFILE, VARIATIONS[0])
    assert prompt.startswith(MASTER_PROFILE.identity_prompt())
    assert assert_identity_preserved(prompt, MASTER_PROFILE)
    for marker in IDENTITY_MARKERS:
        assert marker in prompt


def test_build_prompt_extra_is_last_and_every_variation_preserves_identity():
    extra = "shot on 85mm, 9:16 vertical"
    for variation in VARIATIONS:
        prompt = build_prompt(MASTER_PROFILE, variation, extra)
        assert prompt.startswith(MASTER_PROFILE.identity_prompt())
        assert assert_identity_preserved(prompt, MASTER_PROFILE)
        assert prompt.strip().endswith(extra)


def test_nonexplicit_constraint_present():
    prompt = build_prompt(MASTER_PROFILE, VARIATIONS[0])
    assert "NO NUDITY" in prompt
    assert "non-nude" in prompt
    assert "no nipples no areola no genitalia" in prompt
    assert "adult 25yo" in prompt
    assert "nudity" in MASTER_PROFILE.negative_prompt_text()
    assert "no text watermark logo" in QUALITY_CONSTRAINTS


def test_negatives_identical_and_never_ban_allure_words():
    assert PERCHANCE_NEGATIVE == DEFAULT_NEGATIVE_PROMPT
    for banned_from_negative in ("skinny", "slim", "flat chest", "petite",
                                 "fat", "flabby", "protruding belly", "big stomach",
                                 "shiny skin", "plastic skin", "cartoon", "3d render"):
        assert banned_from_negative in PERCHANCE_NEGATIVE
    for required in ("cleavage", "lingerie", "sexy", "seductive", "curvy", "thick", "fit"):
        assert required not in PERCHANCE_NEGATIVE


def test_allure_v2_body_rules_present_in_every_prompt():
    must_have = ("barely containing the bust", "bare shoulders midriff",
                 "fabric tension across bust and hips", "one strap slipping",
                 "raw matte real skin with visible pores")
    for phrase in must_have:
        assert phrase in ALLURE_V2
    for banned in ("soft belly", "small waist"):
        assert banned not in ALLURE_V2
    assert "NO protruding belly" in ALLURE_V2
    for variation in VARIATIONS:
        prompt = build_prompt(MASTER_PROFILE, variation)
        for phrase in must_have:
            assert phrase in prompt
        assert "soft belly" not in prompt


def test_naughty_actions_injected_and_boring_poses_banned():
    assert len(NAUGHTY_ACTIONS) == 7
    assert "never arms crossed" in POSE_ENFORCEMENT.lower()
    assert "never blank stare" in POSE_ENFORCEMENT.lower()
    seen = set()
    for variation in VARIATIONS:
        prompt = build_prompt(MASTER_PROFILE, variation)
        assert any(action in prompt for action in NAUGHTY_ACTIONS)
        seen.update(a for a in NAUGHTY_ACTIONS if a in prompt)
        assert "Tease action:" in prompt
    assert len(seen) >= 4


def test_select_variation_prefers_unused():
    rng = random.Random(0)
    keys = variation_keys()
    remaining = keys[-1]
    used = keys[:-1]
    chosen = select_variation(used, rng=rng)
    assert chosen.key == remaining, "must pick the one unused key"


def test_select_variation_falls_back_to_least_used():
    rng = random.Random(0)
    keys = variation_keys()
    overused = keys[0]
    used = list(keys) + [overused]  # one key used twice, the rest once
    chosen = select_variation(used, rng=rng)
    assert chosen.key in keys
    assert chosen.key != overused, "least-used keys should be preferred"


def test_select_variation_never_fails_when_empty():
    assert select_variation([], rng=random.Random(1)).key in variation_keys()
    assert select_variation(None, rng=random.Random(1)).key in variation_keys()


def test_with_reference_is_immutable():
    updated = MASTER_PROFILE.with_reference(["ref1.png", "ref2.png"])
    assert updated is not MASTER_PROFILE
    assert updated.reference_images == ["ref1.png", "ref2.png"]
    assert MASTER_PROFILE.reference_images == []
    assert updated.identity_prompt() == MASTER_PROFILE.identity_prompt()


def test_build_consistency_defaults_and_metadata_serialisable():
    config = build_consistency(MASTER_PROFILE, seed=42)
    assert config.fixed_seed == 42
    assert config.reference_images == []
    assert config.provider_supports_reference is False

    referenced = MASTER_PROFILE.with_reference(["ref.png"])
    config = build_consistency(referenced, seed=7)
    assert config.reference_images == ["ref.png"]
    assert config.provider_supports_reference is True

    meta = consistency_metadata(config, referenced)
    assert isinstance(meta, dict)
    assert json.loads(json.dumps(meta)) == meta
    assert meta["fixed_seed"] == 7
    assert meta["reference_count"] == 1
    assert meta["profile_id"] == referenced.id
    assert "do not guarantee face identity" in meta["consistency_note"]


def test_assert_identity_preserved_rejects_dropped_identity():
    prompt = "just a pretty woman in a room, no other details"
    assert not assert_identity_preserved(prompt, MASTER_PROFILE)
