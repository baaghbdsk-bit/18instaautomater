"""
profile.py — canonical identity for the single fictional character.

The fixed identity below is the verbatim foundation for every image prompt.
It is never rewritten by the variation engine: only scene-level details change.

IDENTITY CONSISTENCY CAVEAT (important):
A fixed seed, or repeating the exact same text prompt, does NOT guarantee the
same face across generated images. Image providers interpret prompts
probabilistically, so facial identity will drift from frame to frame.
Reference-image conditioning (passing an ID/reference photo to a provider that
supports it) is a *provider capability*, not a prompt trick — no choice of
words can pin a face by itself. Use ``reference_images`` together with a
provider that genuinely supports reference conditioning, and verify the
output. The text below stabilises the described attributes, not pixel-level
identity.
"""

from dataclasses import dataclass, field, replace

# Canonical identity — kept verbatim. Do not redesign or silently slim her.
FIXED_IDENTITY = (
    "Fictional adult woman, age 25, South Asian Indian appearance, approx 165 cm tall, fair to fair-medium luminous skin with photoreal pores, long voluminous wavy dark chocolate-brown hair with center part cascading over one shoulder, round full-cheeked soft oval face, SAME FACE IN EVERY IMAGE, NEVER change face, large almond-shaped dark brown eyes with thick lashes and winged eyeliner, defined arched eyebrows, delicate straight nose, full glossy rose lips slightly parted with lower lip full, small dark mole below left corner of lips [FACE ANCHOR - never remove], confident seductive lustful expression with bedroom eyes into lens. Body: healthy fit thick curvy hourglass, NOT skinny NOT fat: fuller toned upper arms not flabby, broad smooth shoulders, BIGGER full heavy bust size DD with deep cleavage emphasis held in lace, slim tucked flat fit midriff with narrow toned waist, natural waist curve no abs lines, wide curvy hips ratio 0.7, rounded full lifted butt, very thick fit thighs with soft inner touch but no cellulite exaggeration. Skin glowing sunkissed. Style: ultra-alluring teasing slutty-chic male-gaze lust-appealing sexually pleasing, glamorous bold flirty seductive fashion-forward, provocative tease but NO NUDITY. Always adult fictional. Never transform to skinny/slim/petite/flat-chest. Never transform to fat/flabby/protruding belly/sagging."
)

# Unified negative prompt — bans only hard NSFW/anatomy/identity-drift terms.
# NEVER bans: cleavage, lingerie, underwear, see-through, sexy, seductive,
# alluring — those are REQUIRED for the alluring look.
DEFAULT_NEGATIVE_PROMPT = (
    "nudity, nipples, areola, genitalia, pubic hair, explicit sexual activity, "
    "porn, minors, child, teenage, underage, skinny, slim, thin body, anorexic, "
    "flat chest, small bust, petite, toned abs, fat, flabby, obese, protruding "
    "belly, big stomach, sagging belly, different face, different-looking "
    "character, face change, distorted facial features, deformed hands, extra "
    "fingers, duplicated limbs, visible text, watermark, logo, low quality, "
    "blurry, cartoon, illustration"
)


@dataclass(frozen=True)
class CharacterProfile:
    """
    Immutable descriptor for the single canonical fictional influencer.

    See the module docstring for the identity-consistency caveat: a fixed seed
    or repeated prompt does not guarantee face identity, and reference-image
    conditioning is a provider capability rather than a prompt trick.
    """

    id: str = "master"
    version: str = "1.0"
    fixed_identity: str = FIXED_IDENTITY
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT
    reference_images: list = field(default_factory=list)
    style_preset: str = "glamour_editorial"
    notes: str = ""

    def identity_prompt(self) -> str:
        """Return the fixed identity verbatim (never altered by variations)."""
        return self.fixed_identity

    def negative_prompt_text(self) -> str:
        """Return the negative prompt text (non-explicit / safety constraints)."""
        return self.negative_prompt

    def to_dict(self) -> dict:
        """Plain, JSON-serialisable snapshot of the profile."""
        return {
            "id": self.id,
            "version": self.version,
            "fixed_identity": self.fixed_identity,
            "negative_prompt": self.negative_prompt,
            "reference_images": list(self.reference_images),
            "style_preset": self.style_preset,
            "notes": self.notes,
        }

    def with_reference(self, images) -> "CharacterProfile":
        """Return a NEW profile with the given reference images; leave self intact."""
        if images is None:
            images = []
        return replace(self, reference_images=list(images))


MASTER_PROFILE = CharacterProfile(
    id="ai_influencer_01",
    version="1.0.0",
    fixed_identity=FIXED_IDENTITY,
    negative_prompt=DEFAULT_NEGATIVE_PROMPT,
    reference_images=[],
    style_preset="glamour_editorial",
    notes=(
        "Single canonical fictional adult South Asian influencer. Keep the "
        "curvy hourglass build; never convert to a slim/skinny character. "
        "Tasteful fashion, swimwear or non-explicit lingerie is allowed; "
        "nudity and explicit sexual activity are not. Use reference-image "
        "conditioning where the provider supports it for face consistency."
    ),
)
