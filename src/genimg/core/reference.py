"""
Reference image handling for genimg.

This module handles uploading, validating, processing, and encoding reference images
for use with image generation APIs.
"""

import base64
import hashlib
import io
from pathlib import Path
from typing import Optional, Tuple, Union

from PIL import Image

from genimg.core.config import Config, get_config
from genimg.utils.exceptions import ImageProcessingError, ValidationError

# Supported image formats
SUPPORTED_FORMATS = {"PNG", "JPEG", "JPG", "WEBP", "HEIC", "HEIF"}


def _infer_format_from_magic(data: bytes) -> Optional[str]:
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


def _normalize_format(fmt: Optional[str]) -> Optional[str]:
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


def _parse_data_url(data_url: str) -> Tuple[bytes, Optional[str]]:
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
    if mime.startswith("image/"):
        fmt = mime.split("/", 1)[1].split("+")[0].strip()
    else:
        fmt = None
    return payload, _normalize_format(fmt) if fmt else None


def _load_image_source(
    source: Union[str, Path, bytes],
    format_hint: Optional[str] = None,
) -> Tuple[Image.Image, str]:
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


def resize_image(image: Image.Image, max_pixels: Optional[int] = None) -> Image.Image:
    """
    Resize an image to fit within a maximum pixel count while maintaining aspect ratio.

    Args:
        image: PIL Image to resize
        max_pixels: Maximum number of pixels (width * height). If None, uses config default.

    Returns:
        Resized PIL Image (or original if already small enough)
    """
    if max_pixels is None:
        config = get_config()
        max_pixels = config.max_image_pixels

    width, height = image.size
    current_pixels = width * height

    if current_pixels <= max_pixels:
        return image  # No resize needed

    # Calculate new dimensions maintaining aspect ratio
    scale_factor = (max_pixels / current_pixels) ** 0.5
    new_width = int(width * scale_factor)
    new_height = int(height * scale_factor)

    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


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
    source: Union[str, Path, bytes],
    format_hint: Optional[str] = None,
    max_pixels: Optional[int] = None,
    config: Optional[Config] = None,
) -> Tuple[str, str]:
    """
    Process a reference image for API submission.

    This function:
    1. Validates the image format
    2. Loads the image (from file path or in-memory bytes)
    3. Resizes if needed
    4. Converts to RGB
    5. Encodes to base64

    Args:
        source: Path to the image file (str or Path) or raw image bytes
        format_hint: Optional format when source is bytes (e.g. 'PNG', 'JPEG', 'image/jpeg')
        max_pixels: Maximum number of pixels (defaults to config value)
        config: Optional config to use for max_pixels when not provided; if None, uses get_config()

    Returns:
        Tuple of (base64_encoded_image, image_hash)

    Raises:
        ValidationError: If image format is invalid
        ImageProcessingError: If processing fails
        FileNotFoundError: If file doesn't exist (path source only)
    """
    if max_pixels is None:
        max_pixels = (config or get_config()).max_image_pixels

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

    # Resize if needed
    image = resize_image(image, max_pixels)

    # Convert to RGB
    image = convert_to_rgb(image)

    # Encode to base64 (use JPEG for potentially smaller size)
    encoded = encode_image_base64(image, format="JPEG")

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
