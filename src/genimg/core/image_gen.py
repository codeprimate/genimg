"""
Image generation via selectable providers (OpenRouter, Ollama, etc.).

This module exposes the single public API generate_image() which delegates
to the configured provider via the provider registry.
"""

import io
from collections.abc import Callable
from dataclasses import dataclass

from PIL import Image

from genimg.core.config import Config, get_config
from genimg.core.providers import get_registry
from genimg.logging_config import get_logger
from genimg.utils.exceptions import ValidationError

logger = get_logger(__name__)


@dataclass
class GenerationResult:
    """Result of an image generation operation.

    The primary output is ``image`` (a PIL Image). Use it to save, convert format,
    or get bytes as needed. ``image_data`` and ``format`` are provided for
    backward compatibility.
    """

    image: Image.Image  # PIL Image; caller can save, convert, or get bytes as needed
    _format: str  # Format from API, e.g. 'jpeg' or 'png'
    generation_time: float  # Time taken in seconds
    model_used: str  # Model that generated the image
    prompt_used: str  # Prompt that was used
    had_reference: bool  # Whether a reference image was used

    @property
    def format(self) -> str:
        """Image format from the API (e.g. 'jpeg', 'png')."""
        return self._format

    @property
    def image_data(self) -> bytes:
        """Raw image bytes in the API's format (for backward compatibility)."""
        buf = io.BytesIO()
        self.image.save(buf, format=self._format)
        return buf.getvalue()


def generate_image(
    prompt: str,
    model: str | None = None,
    reference_image_b64: str | None = None,
    provider: str | None = None,
    api_key: str | None = None,
    timeout: int | None = None,
    config: Config | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> GenerationResult:
    """
    Generate an image using the configured provider (default from config).

    Args:
        prompt: Text prompt describing the desired image
        model: Model ID to use (defaults to config value for the chosen provider)
        reference_image_b64: Optional base64-encoded reference image (OpenRouter only)
        provider: Optional provider id (openrouter, ollama); defaults to config.default_image_provider
        api_key: Optional API key (defaults to config value; OpenRouter only)
        timeout: Optional timeout in seconds (defaults to config value)
        config: Optional config to use; if None, uses shared config from get_config()
        cancel_check: Optional callable returning True to cancel; polled during the request.
            Should return quickly and not raise (exceptions are caught and ignored).

    Returns:
        GenerationResult with image data and metadata

    Raises:
        ValidationError: If inputs are invalid (empty prompt, unknown provider, reference with unsupported provider)
        APIError: If API call fails
        NetworkError: If network error occurs
        RequestTimeoutError: If request times out
        CancellationError: If cancel_check returned True
    """
    if not prompt or not prompt.strip():
        raise ValidationError("Prompt cannot be empty", field="prompt")

    config = config or get_config()
    provider_id = provider if provider is not None else config.default_image_provider
    model = model if model is not None else config.default_image_model
    timeout = timeout if timeout is not None else config.generation_timeout

    impl = get_registry().get(provider_id)
    if impl is None:
        raise ValidationError(f"Unknown image provider: {provider_id!r}", field="provider")

    if reference_image_b64 is not None and not getattr(impl, "supports_reference_image", True):
        raise ValidationError(
            f"Reference images are not supported for provider {provider_id!r}. "
            "Use OpenRouter for reference image support.",
            field="reference_image",
        )

    effective_api_key = api_key if api_key is not None else config.openrouter_api_key
    return impl.generate(
        prompt=prompt,
        model=model,
        reference_image_b64=reference_image_b64,
        timeout=timeout,
        config=config,
        cancel_check=cancel_check,
        api_key_override=effective_api_key,
    )
