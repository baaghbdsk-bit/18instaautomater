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
    "teasing non-nude, no nipples no areola no genitalia, raw matte human "
    "skin, visible pores, no distorted features, no duplicated limbs, no "
    "text watermark logo"
)

# Allure emphasis V2 — body shape rules from the owner. Every prompt must
# carry the flat-but-tucked waist AND thick curves so neither "skinny model"
# nor "fat belly" drift is possible.
ALLURE_V2 = (
    "Allure exposure: tiny black lace bralette barely containing the bust, "
    "open red satin robe sliding off the shoulders, very short high-cut "
    "shorts, deep neckline with cleavage emphasis, bare shoulders midriff "
    "and thighs on show, fabric tension across bust and hips, one strap "
    "slipping, hips cocked, chest forward, back arched, hands on body, "
    "parted lips, lustful eye contact, raw matte real skin with visible "
    "pores, FLAT MATTE complexion with zero shine, no specular highlights "
    "anywhere on skin, no wet or dewy sheen, dry chalky skin texture, "
    "diffuse flat window light not direct light, NOT skinny, NOT fat, "
    "NO protruding belly, NO nudity"
)

# Backwards-compatible name for older callers.
ALLURE_BLOCK = ALLURE_V2
PHOTOREAL_BLOCK = (
    "raw amateur phone photo, uneven window daylight, slight film grain "
    "and motion blur, unedited, ordinary messy real room, no studio "
    "lighting, no polish, matte flat skin pixels, no glow, no highlights"
)

# Naughty action bank — a different tease action is injected into every pose,
# so no variation collapses into a plain standing shot.
NAUGHTY_ACTIONS = (
    "grabbing and squeezing her bust over the lace",
    "slowly pulling one strap down her shoulder",
    "hands tracing from collarbone down to cleavage",
    "gripping the shorts hem and pulling it up over her hips",
    "leaning forward with chest up, back arched and hips cocked",
    "sitting on the bed with legs open and knees together, leaning in",
    "looking back over her shoulder with hips pushed back",
)

POSE_ENFORCEMENT = (
    "Pose rule: hips cocked, chest pushed forward, back arched, one hand "
    "touching her body, lips parted, lustful half-lidded eye contact into "
    "the lens. Never standing straight, never arms crossed, never blank stare."
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
        outfit="tiny black lace bralette barely containing bust, open red satin robe off shoulders, very short high-cut shorts",
        pose="grabbing and squeezing her bust over the lace",
        expression="bedroom eyes and parted lips",
        gaze="lustful half-lidded eye contact into the lens",
        camera_angle="intimate POV close-up, low angle",
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
        outfit="tiny black lace bralette barely containing bust, open red satin robe off shoulders, very short high-cut shorts",
        pose="slowly pulling one strap down her shoulder",
        expression="lip bite with lusty smirk",
        gaze="bedroom eyes staring into the lens",
        camera_angle="low angle close-up from the hip",
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
        outfit="tiny black lace bralette barely containing bust, open red satin robe off shoulders, very short high-cut shorts",
        pose="hands tracing from collarbone down to cleavage",
        expression="finger on lips, half-lidded bedroom eyes",
        gaze="lusty look back over shoulder into the lens",
        camera_angle="intimate eye-level close-up",
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
        outfit="tiny black lace bralette barely containing bust, open red satin robe off shoulders, very short high-cut shorts",
        pose="gripping the shorts hem and pulling it up over her hips",
        expression="lusty smirk with parted lips",
        gaze="lustful half-lidded eye contact into the lens",
        camera_angle="intimate POV close-up, low angle",
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
        outfit="tiny black lace bralette barely containing bust, open red satin robe off shoulders, very short high-cut shorts",
        pose="leaning forward with chest up, back arched and hips cocked",
        expression="bedroom eyes and parted lips",
        gaze="bedroom eyes staring into the lens",
        camera_angle="low angle close-up from the hip",
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
        outfit="tiny black lace bralette barely containing bust, open red satin robe off shoulders, very short high-cut shorts",
        pose="sitting on the bed with legs open and knees together, leaning in",
        expression="lip bite with lusty smirk",
        gaze="lusty look back over shoulder into the lens",
        camera_angle="intimate eye-level close-up",
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
        outfit="tiny black lace bralette barely containing bust, open red satin robe off shoulders, very short high-cut shorts",
        pose="looking back over her shoulder with hips pushed back",
        expression="finger on lips, half-lidded bedroom eyes",
        gaze="lustful half-lidded eye contact into the lens",
        camera_angle="intimate POV close-up, low angle",
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
        outfit="tiny black lace bralette barely containing bust, open red satin robe off shoulders, very short high-cut shorts",
        pose="grabbing and squeezing her bust over the lace",
        expression="lusty smirk with parted lips",
        gaze="bedroom eyes staring into the lens",
        camera_angle="low angle close-up from the hip",
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
        outfit="tiny black lace bralette barely containing bust, open red satin robe off shoulders, very short high-cut shorts",
        pose="slowly pulling one strap down her shoulder",
        expression="bedroom eyes and parted lips",
        gaze="lusty look back over shoulder into the lens",
        camera_angle="intimate eye-level close-up",
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
        outfit="tiny black lace bralette barely containing bust, open red satin robe off shoulders, very short high-cut shorts",
        pose="hands tracing from collarbone down to cleavage",
        expression="lip bite with lusty smirk",
        gaze="lustful half-lidded eye contact into the lens",
        camera_angle="intimate POV close-up, low angle",
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
        outfit="tiny black lace bralette barely containing bust, open red satin robe off shoulders, very short high-cut shorts",
        pose="gripping the shorts hem and pulling it up over her hips",
        expression="finger on lips, half-lidded bedroom eyes",
        gaze="bedroom eyes staring into the lens",
        camera_angle="low angle close-up from the hip",
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
        outfit="tiny black lace bralette barely containing bust, open red satin robe off shoulders, very short high-cut shorts",
        pose="leaning forward with chest up, back arched and hips cocked",
        expression="lusty smirk with parted lips",
        gaze="lusty look back over shoulder into the lens",
        camera_angle="intimate eye-level close-up",
        camera_distance="medium shot",
        lighting="warm golden afternoon light",
        environment="urban street with a colorful graffiti wall",
        hair="loose waves under a sleek cap",
        makeup="natural street-style makeup with matte lips",
        accessories="small hoop earrings and a chain necklace",
        mood="urban and self-assured",
    ),
    Variation(
        key="modern_club_corset",
        outfit="sleek black structured satin corset top with deep sweetheart neckline and fitted leather mini skirt",
        pose="leaning forward slightly over a marble bar counter with hips cocked",
        expression="teasing bite-lip smirk, half-lidded bedroom eyes",
        gaze="direct sultry eye contact into the lens",
        camera_angle="slightly low-angle medium close-up",
        camera_distance="medium shot",
        lighting="warm amber neon and soft lounge rim light",
        environment="upscale modern rooftop cocktail lounge at night with city bokeh",
        hair="voluminous glossy dark waves with wispy front strands",
        makeup="smoky winged eyeliner, glossy plum-nude lips, soft cheek blush",
        accessories="delicate layered gold necklaces and small hoop earrings",
        mood="bold, modern, and magnetic",
    ),
    Variation(
        key="hotel_mirror_selfie",
        outfit="fitted charcoal ribbed cropped tank and low-rise tailored lounge pants",
        pose="standing in front of a full-length mirror, one hand on hip, torso angled",
        expression="playful confident half-smile with parted lips",
        gaze="looking through the mirror directly into the phone lens",
        camera_angle="mirror-reflection eye-level",
        camera_distance="three-quarter shot",
        lighting="soft diffused daylight from floor-to-ceiling suite curtains",
        environment="minimalist luxury hotel suite with warm wood paneling",
        hair="messy high-volume waves clipped half-up",
        makeup="natural matte skin, softly defined brows, glossy rose lips",
        accessories="thin silver bracelets and double nose rings",
        mood="intimate, modern, and effortless",
    ),
    Variation(
        key="rooftop_pool_glam",
        outfit="emerald-green halter-neck strappy bikini top with sheer open linen cover-up shirt",
        pose="reclining on a poolside lounger, back arched, one hand resting near collarbone",
        expression="sun-kissed teasing smirk, heavy-lidded eyes",
        gaze="looking back over her shoulder toward the camera",
        camera_angle="slightly high-angle candid portrait",
        camera_distance="medium shot",
        lighting="golden-hour sunset light with warm rim glow",
        environment="modern infinity-edge rooftop pool overlooking skyline",
        hair="damp tousled dark waves over bare shoulders",
        makeup="natural freckles visible, matte complexion, glossy peach lips",
        accessories="tiny gold hoops and delicate belly chain",
        mood="radiant, alluring, and summer-luxury",
    ),
    Variation(
        key="vip_booth_champagne",
        outfit="metallic silver halter crop top with deep plunge and micro-mini black leather skirt",
        pose="leaning back on a velvet VIP club sofa holding a champagne flute, legs crossed, chest forward",
        expression="bold playful smirk with parted glossy lips",
        gaze="direct confident eye contact into the camera",
        camera_angle="slightly high-angle three-quarter shot",
        camera_distance="medium shot",
        lighting="moody magenta and warm amber club spotlighting",
        environment="crowded high-end nightclub VIP booth with glowing bottle service lights",
        hair="big tousled dark waves over bare shoulders",
        makeup="glitter winged liner, bronzed cheekbones, glossy berry lips",
        accessories="statement hoop earrings and stacked rings",
        mood="wild, glamorous, and unapologetic nightlife",
    ),
    Variation(
        key="afterparty_neon_mini",
        outfit="strappy burgundy satin backless mini dress hugging every curve",
        pose="looking back over her shoulder near a neon-lit lounge mirror, hips pushed back",
        expression="sultry half-lidded gaze with a teasing smirk",
        gaze="flirty glance over shoulder into the lens",
        camera_angle="eye-level candid flash photo",
        camera_distance="three-quarter shot",
        lighting="direct 35mm party flash with warm neon background",
        environment="late-night penthouse afterparty with city lights behind glass",
        hair="messy voluminous waves",
        makeup="smoky eyes, matte skin, glossy lips",
        accessories="thin gold anklet, dainty necklace, double nose rings",
        mood="late-night party energy and bold confidence",
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
        PHOTOREAL_BLOCK,
        "Quality constraints: " + QUALITY_CONSTRAINTS,
    ]
    if extra and extra.strip():
        parts.append(extra.strip())
    return "\n".join(parts)
