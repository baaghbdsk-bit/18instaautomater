"""
image_providers/base.py — shared data contracts for image generation.

Every provider takes an :class:`ImageRequest` and returns an :class:`ImageResult`.
Providers never raise on expected failures; they return ``ok=False`` with a
``status`` describing why.  ``status`` is one of:
``generated`` | ``failed`` | ``unsupported`` | ``skipped``.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImageRequest:
    """A single image-generation request.

    ``reference_images`` is deliberately present so callers can express the
    intent, but no bundled provider currently supports it (there is no
    reference-image parameter in the Perchance API or the NVIDIA NIM Flux
    endpoint).  Providers must record this honestly in their result metadata.
    """

    prompt: str
    negative_prompt: str = ""
    aspect_ratio: str = "512x768"
    width: int = 1080
    height: int = 1920
    seed: Optional[str] = None
    model: Optional[str] = None
    num_images: int = 1
    reference_images: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class ImageResult:
    """Outcome of a generation attempt."""

    ok: bool
    path: Optional[str] = None
    provider: str = ""
    model: Optional[str] = None
    seed: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    error: Optional[str] = None
    status: str = ""  # generated|failed|unsupported|skipped


class ImageProvider(ABC):
    """Interface implemented by every image backend."""

    name = ""

    @abstractmethod
    def generate(self, request: ImageRequest) -> ImageResult:
        """Generate an image and return a result (never raise on normal errors)."""

    def health(self) -> bool:
        """Cheap readiness probe. Stateless providers are always ready."""
        return True
