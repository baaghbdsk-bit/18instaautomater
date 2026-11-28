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
    "Fictional adult woman 25 South Asian Indian, 165cm, fair-medium skin with DRY MATTE real human texture visible pores uneven tone faint blemish, NO shine NO oil NO glow, slight asymmetry, long messy voluminous wavy dark brown hair with flyaways center part, oval-round cheeked face SAME FACE EVERY IMAGE, sultry light hazel-green bedroom eyes half-lidded locked onto lens, soft freckles across nose and cheeks, double silver nose rings, small black heart mark below left eye, small mole below left lip [FACE ANCHOR], arched brows, straight nose, full glossy parted lips teasing bite-lip smirk. Body: dramatic curvy hourglass healthy fit NOT skinny NOT fat: toned upper arms, BIG full heavy DD bust deep cleavage emphasis, sculpted tiny narrow toned waist, wide hips rounded full glutes thick toned thighs. Never skinny/flat/petite, never fat/flabby/protruding belly. Style: bold seductive glamour-chic teasing fashion, confident alluring pose, NO NUDITY. Always adult."
)

# Unified negative prompt — bans only hard NSFW/anatomy/identity-drift terms.
# NEVER bans: cleavage, lingerie, underwear, see-through, sexy, seductive,
# alluring — those are REQUIRED for the alluring look.
DEFAULT_NEGATIVE_PROMPT = (
    "nudity, nipples, areola, genitalia, pubic hair, porn, minors, skinny, slim, thin, flat chest, petite, fat, flabby, protruding belly, big stomach, oily skin, shiny skin, dewy glow, specular highlights, sweaty shine, polished, airbrushed, plastic skin, smooth skin, beauty filter, perfect symmetry, cartoon, illustration, 3d render, CGI, doll, face change, distorted face, text, watermark, logo, blurry"
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
    reference_images: list = field(default_factory=lambda: ["character/references/master.jpg"])
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
