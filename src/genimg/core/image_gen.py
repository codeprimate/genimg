"""
Image generation via selectable providers (OpenRouter, Ollama, etc.).

This module exposes the single public API generate_image() which delegates
to the configured provider via the provider registry.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from genimg.core.config import Config, get_config
from genimg.core.providers import get_registry
from genimg.logging_config import get_logger
from genimg.utils.exceptions import ValidationError

logger = get_logger(__name__)

GENIMG_PNG_JSON_KEYWORD = "genimg"
GENIMG_META_SCHEMA_VERSION = 1


def pillow_save_kwargs_for_format(fmt: str) -> dict:
    """Return extra kwargs for PIL ``Image.save`` to shrink PNG output (lossless).

    PNG: maximum zlib compression and optimizer pass (slower encode, smaller files).
    Other formats: no extra kwargs (caller controls format-specific options).
    """
    key = (fmt or "").strip().upper()
    if key == "PNG":
        return {"optimize": True, "compress_level": 9}
    return {}


def is_png_output_format(fmt: str) -> bool:
    """Return True if ``fmt`` is PNG (case-insensitive), for output routing."""
    return (fmt or "").strip().upper() == "PNG"


def build_png_info_for_generation(
    result: GenerationResult,
    *,
    genimg_version: str,
    provider: str,
    optimized: bool,
    cli: Literal["generate", "character"],
    original_prompt: str | None = None,
    user_prompt: str | None = None,
) -> PngInfo:
    """Build PNG text metadata (iTXt) for a CLI-saved generation result.

    Embeds registered keywords ``Software`` (``genimg <version> (<provider>/<model>)``)
    and ``Description`` (final prompt), plus a UTF-8 JSON object under keyword ``genimg``
    (see ``GENIMG_META_SCHEMA_VERSION``).

    ``original_prompt`` is included in JSON only when ``optimized`` is True (user
    prompt before optimization). ``user_prompt`` is included for ``character`` when
    non-empty after strip (optional user text appended to the template).
    """
    meta: dict[str, object] = {
        "genimg_meta_version": GENIMG_META_SCHEMA_VERSION,
        "provider": provider,
        "model": result.model_used,
        "generation_time_s": result.generation_time,
        "had_reference": result.had_reference,
        "optimized": optimized,
        "cli": cli,
        "creation_time": datetime.now(timezone.utc).isoformat(),
    }
    if optimized and original_prompt is not None:
        meta["original_prompt"] = original_prompt
    up = (user_prompt or "").strip()
    if up:
        meta["user_prompt"] = up

    pnginfo = PngInfo()
    pnginfo.add_itxt(
        "Software",
        f"genimg {genimg_version} ({provider}/{result.model_used})",
    )
    pnginfo.add_itxt("Description", result.prompt_used)
    pnginfo.add_itxt(
        GENIMG_PNG_JSON_KEYWORD,
        json.dumps(meta, ensure_ascii=False),
    )
    return pnginfo


def write_generation_png(path: Path | str, result: GenerationResult, pnginfo: PngInfo) -> None:
    """Save ``result.image`` as PNG with the given ``pnginfo`` (embedded text chunks)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    result.image.save(
        p,
        format="PNG",
        pnginfo=pnginfo,
        **pillow_save_kwargs_for_format("PNG"),
    )


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
        self.image.save(buf, format=self._format, **pillow_save_kwargs_for_format(self._format))
        return buf.getvalue()


def generate_image(
    prompt: str,
    model: str | None = None,
    reference_image_b64: str | None = None,
    reference_images_b64: list[str] | None = None,
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
        reference_image_b64: Optional single base64-encoded reference (legacy; OpenRouter).
        reference_images_b64: Optional list of base64-encoded references (OpenRouter).
            Do not pass both ``reference_image_b64`` and ``reference_images_b64`` non-``None``.
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

    if reference_image_b64 is not None and reference_images_b64 is not None:
        raise ValidationError(
            "Use either reference_image_b64 or reference_images_b64, not both.",
            field="reference_image",
        )

    refs: list[str] = []
    if reference_images_b64:
        refs = list(reference_images_b64)
    elif reference_image_b64 is not None:
        refs = [reference_image_b64]

    config = config or get_config()
    provider_id = provider if provider is not None else config.default_image_provider
    model = model if model is not None else config.default_image_model
    timeout = timeout if timeout is not None else config.generation_timeout

    impl = get_registry().get(provider_id)
    if impl is None:
        raise ValidationError(f"Unknown image provider: {provider_id!r}", field="provider")

    if refs and not getattr(impl, "supports_reference_image", True):
        raise ValidationError(
            f"Reference images are not supported for provider {provider_id!r}. "
            "Use OpenRouter for reference image support.",
            field="reference_image",
        )

    effective_api_key = api_key if api_key is not None else config.openrouter_api_key
    result = impl.generate(
        prompt=prompt,
        model=model,
        reference_images_b64=refs or None,
        timeout=timeout,
        config=config,
        cancel_check=cancel_check,
        api_key_override=effective_api_key,
    )
    result.had_reference = bool(refs)
    return result
