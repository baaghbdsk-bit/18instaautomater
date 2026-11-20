"""
variations.py — curated, coherent scene variations for the one character.

Each Variation is a complete photographic scene: outfit, pose, lighting and
environment are chosen to agree with one another (e.g. silk robe + bedroom +
seated pose + soft window light). Nothing here changes the fixed identity —
build_prompt() always prepends it verbatim.

All combinations are tasteful and platform-conscious: fashion, swimwear and
non-explicit lingerie are fine, but nudity and explicit sexual activity are
never allowed.
"""

import random
from dataclasses import dataclass

from character.profile import CharacterProfile

# Every dimension that makes up a complete scene (except the identity itself).
DIMENSIONS = (
    "key", "outfit", "pose", "expression", "gaze", "camera_angle",
    "camera_distance", "lighting", "environment", "hair", "makeup",
    "accessories", "mood",
)

# Quality constraints appended to every prompt. "adult subject" and the
# non-explicit/no-nudity clauses are deliberate platform-safety guardrails.
QUALITY_CONSTRAINTS = (
    "realistic anatomy, natural hands and fingers, consistent facial "
    "features, natural body proportions, high-quality photographic "
    "appearance, no distorted facial features, no duplicated limbs, no "
    "visible text or watermark, no unintended artifacts, adult subject, "
    "non-explicit, no nudity"
)


@dataclass(frozen=True)
class Variation:
    key: str
    outfit: str
    pose: str
    expression: str
    gaze: str
    camera_angle: str
    camera_distance: str
    lighting: str
    environment: str
    hair: str
    makeup: str
    accessories: str
    mood: str


# 12 hand-curated, internally coherent scenes (no random recombination).
VARIATIONS = [
    Variation(
        key="silk_robe_bedroom",
        outfit="luxurious champagne silk robe",
        pose="seated upright on a plush bed with one leg tucked beneath her",
        expression="soft confident smile",
        gaze="direct eye contact with the camera",
        camera_angle="eye-level three-quarter angle",
        camera_distance="medium close-up portrait",
        lighting="soft window light filtered through sheer curtains",
        environment="warm sunlit bedroom with cream linens",
        hair="loose waves cascading over one shoulder",
        makeup="dewy natural glamour with soft rose lips",
        accessories="delicate gold hoop earrings",
        mood="intimate and calm",
    ),
    Variation(
        key="neon_night_street",
        outfit="sleek black satin slip dress with a fitted leather jacket",
        pose="standing against a wall, one hand relaxed in her pocket",
        expression="confident smirk",
        gaze="looking slightly past the camera",
        camera_angle="low three-quarter angle",
        camera_distance="medium full-body shot",
        lighting="teal and magenta neon glow",
        environment="rain-slick city street at night with bokeh lights",
        hair="voluminous waves lifted by the breeze",
        makeup="bold winged eyeliner with deep berry lips",
        accessories="thin silver chain necklace",
        mood="bold and electric",
    ),
    Variation(
        key="golden_hour_beach",
        outfit="flowing white summer sundress",
        pose="walking along the shoreline, hem moving in the wind",
        expression="carefree laugh",
        gaze="looking toward the horizon",
        camera_angle="eye-level candid angle",
        camera_distance="medium-wide shot",
        lighting="warm golden hour backlight",
        environment="tropical beach with soft rolling waves",
        hair="wind-tousled waves",
        makeup="sun-kissed glow with glossy nude lips",
        accessories="straw sun hat and small gold studs",
        mood="dreamy and free",
    ),
    Variation(
        key="studio_fashion_editorial",
        outfit="structured emerald velvet gown",
        pose="standing tall, shoulders back, one hand on her hip",
        expression="fierce composed expression",
        gaze="direct intense eye contact",
        camera_angle="straight-on eye-level angle",
        camera_distance="full-length fashion shot",
        lighting="dramatic studio key light with soft fill",
        environment="seamless deep charcoal studio backdrop",
        hair="sleek polished waves swept to one side",
        makeup="contoured editorial glamour with bold red lips",
        accessories="statement chandelier earrings",
        mood="high fashion and commanding",
    ),
    Variation(
        key="cafe_window_candid",
        outfit="cosy oversized cream knit sweater",
        pose="seated by a window, cradling a ceramic mug",
        expression="warm gentle smile",
        gaze="glancing out of the window",
        camera_angle="slightly elevated candid angle",
        camera_distance="medium close-up",
        lighting="soft diffused daylight",
        environment="cosy corner cafe with plants and wooden tables",
        hair="loose waves pinned behind one ear",
        makeup="fresh minimal makeup with tinted lip balm",
        accessories="thin gold pendant necklace",
        mood="relaxed and intimate",
    ),
    Variation(
        key="rooftop_pool_dusk",
        outfit="elegant navy wrap swimsuit with a sheer cover-up",
        pose="lounging on a sun lounger, legs gracefully crossed",
        expression="playful confident smile",
        gaze="looking back over her shoulder at the camera",
        camera_angle="slightly elevated three-quarter angle",
        camera_distance="medium-full shot",
        lighting="soft dusk light with warm string lights",
        environment="rooftop infinity pool overlooking the skyline",
        hair="loose damp waves",
        makeup="waterproof glow with coral lips",
        accessories="large sunglasses pushed into her hair",
        mood="luxurious and carefree",
    ),
    Variation(
        key="office_chic_blazer",
        outfit="tailored charcoal blazer over a silk camisole",
        pose="seated at a desk, leaning forward slightly",
        expression="focused confident expression",
        gaze="direct steady eye contact",
        camera_angle="eye-level portrait angle",
        camera_distance="medium close-up",
        lighting="soft desk lamp glow mixed with window light",
        environment="modern office with a bright city view",
        hair="smooth waves tucked behind both ears",
        makeup="polished professional glamour with nude-pink lips",
        accessories="minimal gold studs and a slim watch",
        mood="poised and ambitious",
    ),
    Variation(
        key="rainy_window_moody",
        outfit="soft grey cashmere cardigan over a simple dress",
        pose="standing beside a rain-streaked window, arms folded",
        expression="thoughtful wistful expression",
        gaze="looking out at the rain",
        camera_angle="side three-quarter angle",
        camera_distance="medium shot",
        lighting="cool grey diffused daylight",
        environment="quiet apartment with rain on the window",
        hair="soft waves falling loosely",
        makeup="subtle cool-toned makeup with soft lips",
        accessories="delicate silver bracelet",
        mood="calm and introspective",
    ),
    Variation(
        key="vintage_vanity_lingerie",
        outfit="tasteful blush lace lingerie set with a satin robe draped open",
        pose="seated at a vanity mirror, adjusting her hair",
        expression="soft flirty smile",
        gaze="meeting her reflection's gaze",
        camera_angle="over-the-shoulder angle",
        camera_distance="medium close-up",
        lighting="warm vanity bulb glow",
        environment="elegant dressing room with a vintage vanity",
        hair="soft waves cascading down her back",
        makeup="classic glamour with defined eyes and rosy lips",
        accessories="pearl drop earrings",
        mood="playful and alluring",
    ),
    Variation(
        key="festival_sunshine",
        outfit="colorful bohemian maxi dress",
        pose="dancing with arms lifted slightly",
        expression="joyful bright smile",
        gaze="looking straight into the camera",
        camera_angle="slightly low candid angle",
        camera_distance="medium-wide shot",
        lighting="bright warm afternoon sun",
        environment="outdoor summer festival with fairy lights",
        hair="loose waves with a flower crown",
        makeup="fresh dewy makeup with peachy lips",
        accessories="flower crown and layered bracelets",
        mood="carefree and vibrant",
    ),
    Variation(
        key="marble_staircase_glamour",
        outfit="floor-length burgundy sequin evening gown",
        pose="descending a marble staircase, one hand on the railing",
        expression="serene confident smile",
        gaze="looking down toward the camera",
        camera_angle="slightly elevated angle",
        camera_distance="full-length shot",
        lighting="warm chandelier light",
        environment="grand interior with a curved marble staircase",
        hair="glossy waves swept over one shoulder",
        makeup="radiant evening glamour with deep red lips",
        accessories="diamond-look drop earrings",
        mood="elegant and dramatic",
    ),
    Variation(
        key="streetwear_golden",
        outfit="oversized stylish streetwear jacket with fitted trousers",
        pose="leaning casually against a graffiti wall, arms crossed",
        expression="cool confident smirk",
        gaze="looking directly at the camera",
        camera_angle="eye-level street angle",
        camera_distance="medium shot",
        lighting="warm golden afternoon light",
        environment="urban street with a colorful graffiti wall",
        hair="loose waves under a sleek cap",
        makeup="natural street-style makeup with matte lips",
        accessories="small hoop earrings and a chain necklace",
        mood="urban and self-assured",
    ),
]

VARIATION_KEYS = [v.key for v in VARIATIONS]


def variation_keys() -> list:
    """Return all curated variation keys in declaration order."""
    return list(VARIATION_KEYS)


def get_variation(key: str) -> Variation:
    """Return the variation for ``key``; fall back to the first if unknown."""
    for variation in VARIATIONS:
        if variation.key == key:
            return variation
    print(f"[variations] unknown key {key!r}, falling back to {VARIATION_KEYS[0]}")
    return VARIATIONS[0]


def select_variation(used_keys, rng=None) -> Variation:
    """
    Prefer an unused variation; if all were used, pick a least-used one.

    ``used_keys`` may contain duplicates to record how many times each key has
    already been used. ``rng`` accepts a ``random.Random`` instance (or any
    object with a ``choice`` method); it defaults to the ``random`` module.
    """
    rng = rng or random
    counts = {}
    for key in used_keys or []:
        counts[key] = counts.get(key, 0) + 1

    unused = [key for key in VARIATION_KEYS if counts.get(key, 0) == 0]
    if unused:
        return get_variation(rng.choice(unused))

    least = min(counts.get(key, 0) for key in VARIATION_KEYS)
    least_used = [key for key in VARIATION_KEYS if counts.get(key, 0) == least]
    return get_variation(rng.choice(least_used))


def build_prompt(profile: CharacterProfile, variation: Variation,
                 extra: str = "") -> str:
    """
    Build one complete prompt: fixed identity FIRST, then scene details, then
    quality constraints, then any caller-supplied extra text.

    The identity is taken verbatim from the profile and is never altered, so
    distinctive canonical phrases always survive every variation.
    """
    scene = ", ".join(
        [
            variation.outfit,
            variation.pose,
            variation.expression,
            variation.gaze,
            variation.camera_angle,
            variation.camera_distance,
            variation.lighting,
            variation.environment,
            variation.hair,
            variation.makeup,
            variation.accessories,
            variation.mood,
        ]
    )
    parts = [
        profile.identity_prompt(),
        "Scene details: " + scene,
        "Quality constraints: " + QUALITY_CONSTRAINTS,
    ]
    if extra and extra.strip():
        parts.append(extra.strip())
    return "\n".join(parts)
