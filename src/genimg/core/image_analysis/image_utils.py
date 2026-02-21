"""
Shared image normalization for image analysis.

Converts path, bytes, or PIL Image to RGB PIL. Both Florence-2 and JoyTag
backends require RGB PIL input. Delegates to reference.load_image_to_rgb_pil
so loading and format validation stay in one place.
"""

from pathlib import Path

from PIL import Image

from genimg.core.reference import load_image_to_rgb_pil


def normalize_image_to_rgb_pil(
    source: Image.Image | str | Path | bytes,
    format_hint: str | None = None,
) -> Image.Image:
    """
    Normalize an image source to RGB PIL for describe backends.

    Accepts PIL Image, file path (str or Path), or raw bytes. Returns
    a PIL Image in RGB mode. Raises ValidationError or ImageProcessingError
    for empty or unsupported input (same as reference image handling).

    Args:
        source: PIL Image, path, or bytes
        format_hint: Optional format hint when source is bytes (e.g. 'PNG', 'JPEG')

    Returns:
        PIL Image in RGB mode

    Raises:
        ValidationError: Unsupported format or empty input
        ImageProcessingError: Load or decode failure
    """
    return load_image_to_rgb_pil(source, format_hint=format_hint)
