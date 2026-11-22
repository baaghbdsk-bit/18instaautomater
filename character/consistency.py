"""
consistency.py — seed/reference config and identity-preservation guardrails.

IMPORTANT: nothing in this module guarantees facial consistency. A fixed seed
or a repeated prompt does NOT pin a face. Reference-image conditioning is a
provider capability, not a prompt trick; ``provider_supports_reference`` only
records whether references are being requested, and must be verified against
the actual image provider. These helpers keep the described attributes stable
and make sure a future variation cannot silently drop the canonical identity.
"""

from dataclasses import dataclass, field

from character.profile import CharacterProfile

# A few distinctive canonical phrases used as an identity-preservation check.
# Each is a substring of the fixed identity in profile.FIXED_IDENTITY.
IDENTITY_MARKERS = (
    "South Asian Indian appearance",
    "dark chocolate-brown hair with center part",
    "almond-shaped dark brown eyes with thick lashes",
    "healthy fit thick curvy hourglass",
    "small dark mole below left corner of lips",
    "SAME FACE IN EVERY IMAGE",
)


@dataclass
class ConsistencyConfig:
    fixed_seed: int | None = None
    reference_images: list = field(default_factory=list)
    provider_supports_reference: bool = False


def build_consistency(profile: CharacterProfile, seed: int | None = None,
                      reference_images=None) -> ConsistencyConfig:
    """
    Build a consistency config from a profile, optional seed and references.

    If ``reference_images`` is None the profile's references are used. The seed
    only stabilises sampling noise; it does not guarantee the same face.
    """
    refs = profile.reference_images if reference_images is None else reference_images
    refs = list(refs or [])
    return ConsistencyConfig(
        fixed_seed=seed,
        reference_images=refs,
        provider_supports_reference=bool(refs),
    )


def consistency_metadata(config: ConsistencyConfig,
                         profile: CharacterProfile) -> dict:
    """Return a plain, JSON-serialisable dict suitable for DB storage."""
    return {
        "profile_id": profile.id,
        "profile_version": profile.version,
        "fixed_seed": config.fixed_seed,
        "reference_images": list(config.reference_images),
        "reference_count": len(config.reference_images),
        "provider_supports_reference": bool(config.provider_supports_reference),
        "style_preset": profile.style_preset,
        "identity_markers": list(IDENTITY_MARKERS),
        "consistency_note": (
            "Fixed seed and repeated prompts do not guarantee face identity; "
            "reference-image conditioning depends on provider support."
        ),
    }


def assert_identity_preserved(prompt: str, profile: CharacterProfile) -> bool:
    """
    True when the prompt still contains the distinctive canonical phrases.

    This is a guard against identity *drift in the text* (e.g. a future
    variation silently dropping the fixed identity). It is NOT a claim that
    the generated image will have a consistent face.
    """
    text = prompt or ""
    identity = profile.identity_prompt()
    markers = [m for m in IDENTITY_MARKERS if m in identity]
    return bool(markers) and all(m in text for m in markers)
