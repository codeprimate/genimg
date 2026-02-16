"""
Reference image handling for genimg.

This module handles uploading, validating, processing, and encoding reference images
for use with image generation APIs.
"""

import base64
import hashlib
import io
import time
from pathlib import Path
from typing import Any, cast

from PIL import Image

from genimg.core.config import Config, get_config
from genimg.logging_config import get_logger
from genimg.utils.exceptions import ImageProcessingError, ValidationError

logger = get_logger(__name__)

# Supported image formats
SUPPORTED_FORMATS = {"PNG", "JPEG", "JPG", "WEBP", "HEIC", "HEIF"}


def _infer_format_from_magic(data: bytes) -> str | None:
    """Infer image format from magic bytes. Returns format name (e.g. PNG, JPEG) or None."""
    if len(data) < 12:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if data[:2] == b"\xff\xd8":
        return "JPEG"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1"):
        return "HEIC"
    return None


def _normalize_format(fmt: str | None) -> str | None:
    """Normalize format to a key present in SUPPORTED_FORMATS (e.g. JPG -> JPEG, image/jpeg -> JPEG)."""
    if not fmt:
        return None
    s = fmt.strip().lower()
    if s.startswith("image/"):
        s = s.split("/", 1)[1]
    u = s.upper()
    if u == "JPG":
        return "JPEG"
    return u if u in SUPPORTED_FORMATS else None


def _parse_data_url(data_url: str) -> tuple[bytes, str | None]:
    """
    Parse a data URL (data:image/xxx;base64,yyy) into raw bytes and MIME format.

    Returns:
        (decoded_bytes, format_hint from MIME e.g. 'PNG', 'JPEG') or raises.
    """
    data_url = data_url.strip()
    if not data_url.startswith("data:"):
        raise ValidationError("Not a data URL", field="image")
    idx = data_url.find(";base64,")
    if idx == -1:
        raise ValidationError("Data URL missing ;base64, part", field="image")
    try:
        payload = base64.b64decode(data_url[idx + 8 :], validate=True)
    except Exception as e:
        raise ValidationError(f"Invalid base64 in data URL: {e}") from e
    mime = data_url[5:idx].strip().lower()
    fmt = mime.split("/", 1)[1].split("+")[0].strip() if mime.startswith("image/") else None
    return payload, _normalize_format(fmt) if fmt else None


def _load_image_source(
    source: str | Path | bytes,
    format_hint: str | None = None,
) -> tuple[Image.Image, str]:
    """
    Load an image from a file path or in-memory bytes.

    Args:
        source: Path to image file (str or Path) or raw image bytes
        format_hint: Optional format/MIME hint when source is bytes (e.g. 'PNG', 'image/jpeg')

    Returns:
        Tuple of (PIL Image, normalized format name for encoding)

    Raises:
        ValidationError: If format is unsupported or cannot be inferred
        ImageProcessingError: If image cannot be loaded
    """
    if isinstance(source, bytes):
        if not source:
            raise ValidationError("Image data is empty", field="image")
        fmt = _normalize_format(format_hint)
        if not fmt:
            inferred = _infer_format_from_magic(source)
            fmt = _normalize_format(inferred) if inferred else None
        if not fmt or fmt not in SUPPORTED_FORMATS:
            raise ValidationError(
                "Could not determine image format from bytes. "
                "Pass format_hint (e.g. 'PNG', 'JPEG', 'image/jpeg').",
                field="image_format",
            )
        try:
            try:
                from pillow_heif import register_heif_opener

                register_heif_opener()
            except ImportError:
                pass
            image = Image.open(io.BytesIO(source))
            image.load()
            return image, fmt
        except Exception as e:
            raise ImageProcessingError(f"Failed to load image from bytes: {str(e)}") from e

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    suffix = path.suffix.upper().lstrip(".")
    if suffix == "JPG":
        suffix = "JPEG"
    if suffix not in SUPPORTED_FORMATS:
        raise ValidationError(
            f"Unsupported image format: {suffix}. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}",
            field="image_format",
        )
    image = load_image(str(path))
    return image, suffix


def validate_image_format(image_path: str) -> None:
    """
    Validate that an image file has a supported format.

    Args:
        image_path: Path to the image file

    Raises:
        ValidationError: If format is not supported
        FileNotFoundError: If file doesn't exist
    """
    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    suffix = path.suffix.upper().lstrip(".")
    if suffix not in SUPPORTED_FORMATS:
        raise ValidationError(
            f"Unsupported image format: {suffix}. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}",
            field="image_format",
        )


def load_image(image_path: str) -> Image.Image:
    """
    Load an image from file.

    Args:
        image_path: Path to the image file

    Returns:
        PIL Image object

    Raises:
        ImageProcessingError: If image cannot be loaded
    """
    try:
        # Try to register HEIF opener if available
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except ImportError:
            pass  # HEIF support not available

        image = Image.open(image_path)
        # Load the image data
        image.load()
        return image

    except Exception as e:
        raise ImageProcessingError(f"Failed to load image: {str(e)}", image_path=image_path) from e


def _pad_to_aspect(
    image: Image.Image,
    aspect_ratio: tuple[int, int],
    fill: tuple[int, ...] = (255, 255, 255),
) -> Image.Image:
    """
    Pad image to match target aspect ratio (width, height) with fill color.
    Pads top/bottom or left/right so the image is centered.
    """
    out_w, out_h = image.size
    if image.mode in ("RGBA", "LA") and len(fill) == 3:
        fill = (*fill, 255)
    ar_w, ar_h = aspect_ratio
    target_ratio = ar_w / ar_h
    current_ratio = out_w / out_h if out_h else 0

    if current_ratio <= target_ratio:
        final_w = max(out_w, round(out_h * target_ratio))
        final_h = out_h
    else:
        final_w = out_w
        final_h = max(out_h, round(out_w / target_ratio))

    if (final_w, final_h) == (out_w, out_h):
        return image

    # PIL Image.new fill accepts int or tuple of 1–4 ints; we pass tuple[int, ...]
    canvas = Image.new(image.mode, (final_w, final_h), cast(Any, fill))
    paste_x = (final_w - out_w) // 2
    paste_y = (final_h - out_h) // 2
    canvas.paste(image, (paste_x, paste_y))
    return canvas


def resize_image(
    image: Image.Image,
    max_pixels: int | None = None,
    min_pixels: int | None = None,
    aspect_ratio: tuple[int, int] | None = None,
) -> Image.Image:
    """
    Resize an image to fit within a maximum pixel count while maintaining aspect ratio,
    then pad to match the configured aspect ratio (white by default).

    Enforces a minimum pixel count (raises ValidationError if output would be too small).

    Args:
        image: PIL Image to resize
        max_pixels: Maximum number of pixels (width * height). If None, uses config default.
        min_pixels: Minimum number of pixels for the result. If None, uses config default.
            If the image (after any resize) would have fewer pixels, ValidationError is raised.
        aspect_ratio: (width, height) ratio for final image; images are padded to match.
            If None, uses config default.

    Returns:
        Resized (and optionally padded) PIL Image

    Raises:
        ValidationError: If the resulting image would have fewer than min_pixels
    """
    if max_pixels is None or min_pixels is None or aspect_ratio is None:
        config = get_config()
        if max_pixels is None:
            max_pixels = config.max_image_pixels
        if min_pixels is None:
            min_pixels = config.min_image_pixels
        if aspect_ratio is None:
            aspect_ratio = config.aspect_ratio

    width, height = image.size
    current_pixels = width * height

    # Compute target dimensions (within max_pixels, aspect ratio preserved)
    if current_pixels <= max_pixels:
        out_w, out_h = width, height
        logger.debug(
            "Reference image no resize needed dimensions=%dx%d max_pixels=%s",
            width,
            height,
            max_pixels,
        )
    else:
        scale_factor = (max_pixels / current_pixels) ** 0.5
        min_dim = min(width, height)
        if min_dim > 0:
            scale_factor = max(scale_factor, 1.0 / min_dim)
        out_w = max(1, int(width * scale_factor))
        out_h = max(1, int(height * scale_factor))
        logger.debug(
            "Reference image resizing %dx%d -> %dx%d max_pixels=%s",
            width,
            height,
            out_w,
            out_h,
            max_pixels,
        )

    out_pixels = out_w * out_h
    if out_pixels < min_pixels:
        raise ValidationError(
            f"Reference image too small: {out_w}x{out_h} ({out_pixels} pixels) "
            f"is below minimum {min_pixels} pixels.",
            field="image",
        )

    if (out_w, out_h) != (width, height):
        image = image.resize((out_w, out_h), Image.Resampling.LANCZOS)

    return _pad_to_aspect(image, aspect_ratio)


def convert_to_rgb(image: Image.Image) -> Image.Image:
    """
    Convert an image to RGB mode if it's not already.

    Args:
        image: PIL Image

    Returns:
        PIL Image in RGB mode
    """
    if image.mode != "RGB":
        # Handle transparency by compositing on white background
        if image.mode == "RGBA" or image.mode == "LA":
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "RGBA":
                background.paste(image, mask=image.split()[3])  # Use alpha channel
            else:
                background.paste(image, mask=image.split()[1])  # Use alpha channel
            return background
        else:
            return image.convert("RGB")
    return image


def encode_image_base64(image: Image.Image, format: str = "PNG") -> str:
    """
    Encode a PIL Image to base64 string.

    Args:
        image: PIL Image to encode
        format: Image format for encoding (PNG or JPEG)

    Returns:
        Base64 encoded image string

    Raises:
        ImageProcessingError: If encoding fails
    """
    try:
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        buffer.seek(0)
        encoded = base64.b64encode(buffer.read()).decode("utf-8")
        return encoded

    except Exception as e:
        raise ImageProcessingError(f"Failed to encode image: {str(e)}") from e


def get_image_hash(image_path: str) -> str:
    """
    Generate a hash of an image file for cache keys.

    Args:
        image_path: Path to the image file

    Returns:
        SHA256 hash of the image file

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    with path.open("rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def process_reference_image(
    source: str | Path | bytes,
    format_hint: str | None = None,
    max_pixels: int | None = None,
    config: Config | None = None,
) -> tuple[str, str]:
    """
    Process a reference image for API submission.

    This function:
    1. Validates the image format
    2. Loads the image (from file path or in-memory bytes)
    3. Resizes if needed (resize_image enforces config max/min pixels)
    4. Converts to RGB
    5. Encodes to base64

    Args:
        source: Path to the image file (str or Path) or raw image bytes
        format_hint: Optional format when source is bytes (e.g. 'PNG', 'JPEG', 'image/jpeg')
        max_pixels: Maximum number of pixels (defaults to config value)
        config: Optional config for max_pixels and min_image_pixels; if None, uses get_config()

    Returns:
        Tuple of (base64_encoded_image, image_hash)

    Raises:
        ValidationError: If image format is invalid or image has fewer pixels than config.min_image_pixels
        ImageProcessingError: If processing fails
        FileNotFoundError: If file doesn't exist (path source only)
    """
    cfg = config or get_config()
    if max_pixels is None:
        max_pixels = cfg.max_image_pixels

    logger.info("Processing reference image max_pixels=%s", max_pixels)
    start_time = time.time()

    # Normalize data URL to bytes so loading and hashing work
    if isinstance(source, str) and source.strip().startswith("data:"):
        source, parsed_fmt = _parse_data_url(source)
        if format_hint is None:
            format_hint = parsed_fmt

    # Load image (validates format for path; for bytes uses format_hint or magic)
    image, _loaded_fmt = _load_image_source(source, format_hint)

    # Hash: from file or from bytes
    if isinstance(source, bytes):
        image_hash = hashlib.sha256(source).hexdigest()
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")
        image_hash = get_image_hash(str(path))

    # Resize if needed (enforces max and min pixels from config)
    image = resize_image(image, max_pixels=max_pixels, min_pixels=cfg.min_image_pixels)

    # Convert to RGB
    image = convert_to_rgb(image)

    # Encode to base64 (use JPEG for potentially smaller size)
    logger.debug("Encoding reference image format=JPEG")
    encoded = encode_image_base64(image, format="JPEG")

    elapsed = time.time() - start_time
    w, h = image.size
    logger.info(
        "Processed reference image in %.2fs dimensions=%dx%d",
        elapsed,
        w,
        h,
    )

    return encoded, image_hash


def create_image_data_url(encoded_image: str, mime_type: str = "image/jpeg") -> str:
    """
    Create a data URL from a base64 encoded image.

    Args:
        encoded_image: Base64 encoded image string
        mime_type: MIME type of the image

    Returns:
        Data URL string
    """
    return f"data:{mime_type};base64,{encoded_image}"
