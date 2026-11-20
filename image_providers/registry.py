"""
image_providers/registry.py — provider lookup by configuration or explicit name.
"""

import config

from .base import ImageProvider
from .nvidia import NvidiaProvider
from .perchance import PerchanceProvider
from .placeholder import PlaceholderProvider

# Maps a provider name to its (stateless) implementation class.
PROVIDERS = {
    "perchance": PerchanceProvider,
    "placeholder": PlaceholderProvider,
    "nvidia": NvidiaProvider,
}


def available_providers() -> list:
    """Return the sorted list of valid provider names."""
    return sorted(PROVIDERS)


def get_provider(name: str = None) -> ImageProvider:
    """Instantiate a provider. ``name`` defaults to ``config.IMAGE_PROVIDER``."""
    key = (name or config.IMAGE_PROVIDER or "perchance").strip().lower()
    if key not in PROVIDERS:
        raise ValueError(
            f"Unknown image provider {key!r}. "
            f"Valid providers: {', '.join(available_providers())}"
        )
    return PROVIDERS[key]()
