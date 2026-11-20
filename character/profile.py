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
    "Fictional adult woman, age 25, South Asian / Indian appearance, "
    "approx 165 cm tall, fair to fair-medium luminous skin, long voluminous "
    "wavy dark chocolate-brown hair, round full-cheeked soft oval face, large "
    "almond-shaped dark brown eyes, defined eyebrows, delicate nose, full "
    "lips, confident attractive expressive appearance, full-figured thick "
    "healthy curvy hourglass body, fuller upper arms, broad shoulders, "
    "proportionate prominent bust, natural waist and soft belly, wide hips "
    "and thick thighs. Never silently transform her into a skinny/slim or "
    "different-looking character. Style: glamorous, bold, flirty, seductive, "
    "fashion-forward, visually striking, provocative but NON-EXPLICIT. "
    "Always an adult fictional character. No nudity, no explicit sexual "
    "activity."
)

# Negative prompt - reinforces the non-explicit, platform-safe, identity-safe
# boundaries described above.
DEFAULT_NEGATIVE_PROMPT = (
    "nudity, explicit sexual activity, sexually explicit content, topless, "
    "minors, child, teenage, underage, skinny, slim, anorexic, thin body, "
    "different-looking character, distorted facial features, deformed hands, "
    "extra fingers, duplicated limbs, visible text, watermark, signature, "
    "logo, low quality, blurry, unintended artifacts"
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
