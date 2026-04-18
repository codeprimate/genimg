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
from PIL.ExifTags import Base
from PIL.PngImagePlugin import PngInfo

from genimg.core.config import Config, get_config
from genimg.core.providers import get_registry
from genimg.logging_config import get_logger
from genimg.utils.exceptions import ValidationError

logger = get_logger(__name__)

GENIMG_PNG_JSON_KEYWORD = "genimg"
GENIMG_META_SCHEMA_VERSION = 1

CliImageFormat = Literal["png", "jpg", "webp"]
CLI_IMAGE_FORMAT_CHOICES: tuple[str, ...] = ("png", "jpg", "webp")

_EXIF_JSON_MAX_BYTES = 56_000


def _cli_embedded_software_string(
    *, genimg_version: str, provider: str, result: GenerationResult
) -> str:
    """Same ``Software`` string as PNG iTXt / EXIF tag 305 (CLI outputs)."""
    return f"genimg {genimg_version} ({provider}/{result.model_used})"


def _escape_xml_attr(value: str) -> str:
    """Escape ``value`` for use in double-quoted XML attributes."""
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace("\r", "&#13;")
        .replace("\n", "&#10;")
    )


def _build_cli_xmp_bytes(*, software: str) -> bytes:
    """Minimal XMP for CLI WebP (Finder / Spotlight often map ``xmp:CreatorTool`` / ``tiff:Software``)."""
    safe = _escape_xml_attr(software)
    # UTF-8 XMP packet; libwebp muxes as ``XMP `` chunk (Pillow passes through).
    xml = (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" '
        'xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
        'xmlns:tiff="http://ns.adobe.com/tiff/1.0/" '
        f'xmp:CreatorTool="{safe}" '
        f'tiff:Software="{safe}"/>'
        "</rdf:RDF></x:xmpmeta>"
        '<?xpacket end="w"?>'
    )
    return xml.encode("utf-8")


def cli_format_to_extension(fmt: CliImageFormat) -> str:
    """Return canonical disk suffix (with leading dot) for ``fmt`` (``jpg`` -> ``.jpg``)."""
    return {"png": ".png", "jpg": ".jpg", "webp": ".webp"}[fmt]


def apply_format_wins_extension(path: Path, fmt: CliImageFormat) -> Path:
    """Apply ``--format``-wins path coercion (naive :mod:`pathlib` final-suffix swap).

    ``Path.stem`` drops only the last suffix, so ``archive.tar.gz`` with ``webp``
    becomes ``archive.tar.webp``. A basename with no ``pathlib`` suffix but a
    lone trailing dot (e.g. ``out.``) is treated as stem ``out`` plus the
    canonical extension (``out.webp``), not ``out..webp``.
    """
    ext = cli_format_to_extension(fmt)
    name = path.name
    suffix = path.suffix
    if suffix:
        stem_for = path.stem
    elif name.endswith(".") and name not in (".", ".."):
        stem_for = name[:-1]
    else:
        stem_for = path.stem
    return path.parent / f"{stem_for}{ext}"


def pillow_save_kwargs_for_cli_output(fmt: CliImageFormat) -> dict[str, object]:
    """Pillow ``save`` kwargs for CLI-selected disk formats (CLI save path only)."""
    if fmt == "png":
        return dict(pillow_save_kwargs_for_format("PNG"))
    if fmt == "jpg":
        # Chroma subsampling: Pillow default (typically 4:2:0 for photographic RGB).
        return {"quality": 95}
    return {"quality": 95, "method": 6, "lossless": False}


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


def build_generation_cli_meta_dict(
    result: GenerationResult,
    *,
    provider: str,
    optimized: bool,
    cli: Literal["generate", "character"],
    original_prompt: str | None = None,
    user_prompt: str | None = None,
) -> dict[str, object]:
    """JSON-serializable metadata object shared by PNG iTXt and JPEG/WebP EXIF."""
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
    return meta


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
    meta = build_generation_cli_meta_dict(
        result,
        provider=provider,
        optimized=optimized,
        cli=cli,
        original_prompt=original_prompt,
        user_prompt=user_prompt,
    )

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


def _flatten_image_to_rgb_white(image: Image.Image) -> Image.Image:
    """Return ``RGB``, compositing transparency on white (CLI ``--format jpg``)."""
    if image.mode == "RGB":
        return image.copy()
    im = image.copy()
    if im.mode == "P":
        if "transparency" in im.info:
            im = im.convert("RGBA")
        else:
            return im.convert("RGB")
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        return bg
    if im.mode == "LA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        l_, a = im.split()
        rgba = Image.merge("RGBA", (l_, l_, l_, a))
        bg.paste(rgba, mask=a)
        return bg
    return im.convert("RGB")


def _build_cli_exif_bytes(
    result: GenerationResult,
    *,
    genimg_version: str,
    provider: str,
    optimized: bool,
    cli: Literal["generate", "character"],
    original_prompt: str | None,
    user_prompt: str | None,
) -> bytes | None:
    """EXIF blob for JPEG/WebP CLI saves (best-effort; returns ``None`` on failure)."""
    try:
        meta = build_generation_cli_meta_dict(
            result,
            provider=provider,
            optimized=optimized,
            cli=cli,
            original_prompt=original_prompt,
            user_prompt=user_prompt,
        )
        json_str = json.dumps(meta, ensure_ascii=False)
        enc = json_str.encode("utf-8")
        if len(enc) > _EXIF_JSON_MAX_BYTES:
            head = enc[: _EXIF_JSON_MAX_BYTES - 10].decode("utf-8", errors="ignore")
            json_str = head + "\u2026"
        software = _cli_embedded_software_string(
            genimg_version=genimg_version, provider=provider, result=result
        )
        exif = Image.Exif()
        exif[Base.Software] = software
        # Tag 11: name/version of post-processing software (often surfaced as “app” metadata).
        exif[Base.ProcessingSoftware] = software
        exif[Base.ImageDescription] = result.prompt_used
        exif[Base.UserComment] = ("UNICODE\0" + json_str).encode("utf-8")
        return exif.tobytes()
    except Exception as e:
        logger.debug("CLI EXIF metadata build failed (best-effort): %s", e)
        return None


def save_generation_cli(
    result: GenerationResult,
    path: Path | str,
    fmt: CliImageFormat,
    *,
    pnginfo: PngInfo | None = None,
    genimg_version: str,
    provider: str,
    optimized: bool,
    cli: Literal["generate", "character"],
    original_prompt: str | None = None,
    user_prompt: str | None = None,
) -> None:
    """Persist ``result.image`` in CLI-selected disk format (not raw ``image_data``)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "png":
        if pnginfo is None:
            raise ValueError("pnginfo is required when fmt is 'png'")
        write_generation_png(p, result, pnginfo)
        return

    exif_bytes = _build_cli_exif_bytes(
        result,
        genimg_version=genimg_version,
        provider=provider,
        optimized=optimized,
        cli=cli,
        original_prompt=original_prompt,
        user_prompt=user_prompt,
    )
    kw = dict(pillow_save_kwargs_for_cli_output(fmt))
    if fmt == "jpg":
        im = _flatten_image_to_rgb_white(result.image)
        save_kw: dict[str, object] = {"format": "JPEG", **kw}
        if exif_bytes is not None:
            save_kw["exif"] = exif_bytes
        im.save(p, **save_kw)
        return

    im = result.image.copy()
    if im.mode == "P":
        im = im.convert("RGBA")
    software = _cli_embedded_software_string(
        genimg_version=genimg_version, provider=provider, result=result
    )
    save_kw: dict[str, object] = {
        "format": "WEBP",
        **kw,
        "xmp": _build_cli_xmp_bytes(software=software),
    }
    if exif_bytes is not None:
        save_kw["exif"] = exif_bytes
    im.save(p, **save_kw)


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
