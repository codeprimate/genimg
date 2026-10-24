"""
Provider protocol for image generation.

Defines the interface that all image generation providers must implement.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from genimg.core.config import Config

if TYPE_CHECKING:
    from genimg.core.image_gen import GenerationResult


class ImageGenerationProvider(Protocol):
    """Protocol for image generation providers.

    Providers implement HTTP (or equivalent) communication with a backend
    and return a unified GenerationResult.
    """

    @property
    def supports_reference_image(self) -> bool:
        """Whether this provider supports reference images. Read-only."""
        ...

    def generate(
        self,
        prompt: str,
        model: str,
        reference_images_b64: list[str] | None,
        timeout: int,
        config: Config,
        cancel_check: Callable[[], bool] | None,
        *,
        api_key_override: str | None = None,
        aspect_ratio: str | None = None,
        max_extent: int | None = None,
    ) -> GenerationResult:
        """Generate an image from prompt and optional reference images.

        ``reference_images_b64`` may be ``None`` or an empty list when no
        reference images are supplied.

        ``aspect_ratio`` and ``max_extent`` are the normalized size pair.
        Both are ``None`` when the caller omitted the pair. Providers map
        the pair onto their own request. They do not crop or scale the bitmap.

        May raise ValidationError, APIError, NetworkError,
        RequestTimeoutError, or CancellationError.
        """
        ...
