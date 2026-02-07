"""
Reference image handling for genimg.

This module handles uploading, validating, processing, and encoding reference images
for use with image generation APIs.
"""

import base64
import hashlib
import io
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

from genimg.core.config import get_config
from genimg.utils.exceptions import ImageProcessingError, ValidationError

# Supported image formats
SUPPORTED_FORMATS = {"PNG", "JPEG", "JPG", "WEBP", "HEIC", "HEIF"}


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
        raise ImageProcessingError(
            f"Failed to load image: {str(e)}", image_path=image_path
        ) from e


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

    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def process_reference_image(
    image_path: str, max_pixels: Optional[int] = None
) -> Tuple[str, str]:
    """
    Process a reference image for API submission.

    This function:
    1. Validates the image format
    2. Loads the image
    3. Resizes if needed
    4. Converts to RGB
    5. Encodes to base64

    Args:
        image_path: Path to the image file
        max_pixels: Maximum number of pixels (defaults to config value)

    Returns:
        Tuple of (base64_encoded_image, image_hash)

    Raises:
        ValidationError: If image format is invalid
        ImageProcessingError: If processing fails
        FileNotFoundError: If file doesn't exist
    """
    # Validate format
    validate_image_format(image_path)

    # Get hash before processing
    image_hash = get_image_hash(image_path)

    # Load image
    image = load_image(image_path)

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
