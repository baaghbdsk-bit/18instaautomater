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
    "identical consistent facial features, sharp detailed face, adult 25yo, "
    "teasing non-nude, no nipples no areola no genitalia, fit toned healthy "
    "glow, photoreal skin, no distorted features, no duplicated limbs, no "
    "text watermark logo"
)

# Allure emphasis V2 — body shape rules from the owner. Every prompt must
# carry the flat-but-tucked waist AND thick curves so neither "skinny model"
# nor "fat belly" drift is possible.
ALLURE_V2 = (
    "Allure emphasis V2: ultra-sexy body-hugging revealing outfit, short "
    "length, deep neckline with deep cleavage in lace, bare shoulders and "
    "midriff and thighs on show, BIGGER full heavy bust, slim tucked flat fit "
    "midriff and narrow waist, wide hips and thick thighs, rounded full lifted "
    "butt, fit toned healthy glow, sunkissed skin, seductive pose with hips "
    "cocked and chest forward and back slightly arched, one hand on body, "
    "glossy parted lips, lustful eye contact into lens, teasing provocative "
    "mood, Instagram baddie reel aesthetic, sharp focus on face and body, "
    "NOT skinny, NOT fat, NO protruding belly"
)

# Backwards-compatible name for older callers.
ALLURE_BLOCK = ALLURE_V2

# Naughty action bank — a different tease action is injected into every pose,
# so no variation collapses into a plain standing shot.
NAUGHTY_ACTIONS = (
    "grabbing her bust over the lace with one hand",
    "slowly slipping one strap off her shoulder",
    "hand buried in her hair with her back arched",
    "looking back over her shoulder with hips pushed back",
    "sitting on the edge of the bed leaning forward toward the camera",
)

POSE_ENFORCEMENT = (
    "Pose rule: hips cocked, chest pushed forward, back slightly arched, one "
    "hand on her body, lips parted, lustful eye contact into the lens. Never "
    "standing straight, never arms crossed, never blank stare."
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
        outfit="champagne silk robe worn open over a satin camisole and high-cut shorts",
        pose="seated upright on a plush bed, hips tilted, one leg tucked beneath her",
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
        outfit="thin-strap black satin mini slip dress with a cropped leather jacket left open",
        pose="leaning against a wall, hip cocked out, chest forward, one hand on her hip",
        expression="confident seductive smirk",
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
        outfit="high-cut coral bikini with tie-side bottoms",
        pose="hip cocked, shoulders back, one hand on her hip, the other brushing her hair",
        expression="seductive playful smile",
        gaze="lustful eye contact into the lens",
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
        outfit="black satin mini slip dress with thin straps and a plunging neckline",
        pose="hips cocked and pushed forward, back arched, one hand on her hip",
        expression="fierce seductive gaze",
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
        outfit="fitted silk blouse with the top buttons open and a high-waisted pencil skirt",
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
        outfit="high-cut emerald green bikini with gold details",
        pose="leaning back on a sun lounger, hips raised, legs crossed",
        expression="seductive confident smile",
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
        outfit="unbuttoned tailored charcoal blazer over a silk camisole",
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
        pose="leaning beside a rain-streaked window, hip cocked, one hand on her waist",
        expression="lustful parted-lip expression",
        gaze="lustful eye contact into the lens",
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
        outfit="black lace lingerie set with a satin robe draped open",
        pose="seated at a vanity mirror, arched back slightly, one hand on her hip",
        expression="soft seductive smile",
        gaze="lustful eye contact into the lens",
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
        outfit="royal blue bikini top with high-waisted denim shorts",
        pose="dancing with arms lifted slightly, hips swaying",
        expression="bright teasing smile",
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
        outfit="burgundy satin mini dress with a thigh-high slit and thin straps",
        pose="descending a marble staircase, hips swaying, one hand on the railing",
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
        outfit="cropped streetwear jacket over a fitted tank top and high-waisted trousers",
        pose="leaning against a graffiti wall, hip cocked, one hand gripping her own waist",
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
    action = NAUGHTY_ACTIONS[VARIATION_KEYS.index(variation.key) % len(NAUGHTY_ACTIONS)]
    parts = [
        profile.identity_prompt(),
        "Scene details: " + scene,
        f"Tease action: {action}. " + POSE_ENFORCEMENT,
        ALLURE_V2,
        "Quality constraints: " + QUALITY_CONSTRAINTS,
    ]
    if extra and extra.strip():
        parts.append(extra.strip())
    return "\n".join(parts)
