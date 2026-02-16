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
        reference_image_b64: str | None,
        timeout: int,
        config: Config,
        cancel_check: Callable[[], bool] | None,
        *,
        api_key_override: str | None = None,
    ) -> GenerationResult:
        """Generate an image from prompt and optional reference.

        May raise ValidationError, APIError, NetworkError,
        RequestTimeoutError, or CancellationError.
        """
        ...
