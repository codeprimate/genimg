"""Caller-facing output size pair and the shared bitmap fit.

Bounds live here as code constants. They are not environment variables and
they are not ``Config`` fields.
"""

from __future__ import annotations

import math
import re

from PIL import Image

from genimg.utils.exceptions import ValidationError

MIN_OUTPUT_EXTENT = 1024
MAX_OUTPUT_EXTENT = 2048
NOMINAL_K_PIXELS = 1024
AUTO_ASPECT_TOKEN = "auto"
MATCH_INPUT_IMAGE_TEXT = "Match Input Image"
MODEL_DEFAULT_LABEL = "Model default"
FIXED_ASPECT_RATIOS = (
    "1:1",
    "5:4",
    "4:5",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "16:9",
    "9:16",
    "auto",
)
WIRO_SIZE_FIELD_IDS = ("aspectRatio", "resolution", "width", "height")

_ASPECT_RATIO_RE = re.compile(r"^(\d+):(\d+)$")
_HALF = 0.5

_MSG_ASPECT_REQUIRED = "aspect_ratio is required when max_extent is set."
_MSG_EXTENT_REQUIRED = "max_extent is required when aspect_ratio is set."
_MSG_ASPECT_TOKEN = "aspect_ratio must be auto or two positive integers separated by a colon."
_MSG_EXTENT_WHOLE = (
    f"max_extent must be a whole number from {MIN_OUTPUT_EXTENT} through {MAX_OUTPUT_EXTENT}."
)
_MSG_EXTENT_RANGE = f"max_extent must be from {MIN_OUTPUT_EXTENT} through {MAX_OUTPUT_EXTENT}."


def round_half_away_from_zero(value: float) -> int:
    """Round ``value`` to an integer. Ties move away from zero."""
    if value >= 0:
        return math.floor(value + _HALF)
    return math.ceil(value - _HALF)


def parse_aspect_ratio(token: str) -> tuple[int, int] | None:
    """Return width and height parts, or ``None`` for ``auto``.

    Raises:
        ValidationError: The token is not ``auto`` and not ``W:H`` of two
            positive integers. ``field`` is ``aspect_ratio``.
    """
    stripped = token.strip()
    if stripped.lower() == AUTO_ASPECT_TOKEN:
        return None
    match = _ASPECT_RATIO_RE.fullmatch(stripped)
    if match is None:
        raise ValidationError(_MSG_ASPECT_TOKEN, field="aspect_ratio")
    width = int(match.group(1))
    height = int(match.group(2))
    if width <= 0 or height <= 0:
        raise ValidationError(_MSG_ASPECT_TOKEN, field="aspect_ratio")
    return width, height


def ideal_pixel_size(aspect_ratio: str, max_extent: int) -> tuple[int, int]:
    """Return width and height whose longer side is ``max_extent``.

    ``auto`` uses a 1:1 ratio. The shorter side may be below
    ``MIN_OUTPUT_EXTENT``.
    """
    parsed = parse_aspect_ratio(aspect_ratio)
    if parsed is None:
        ratio_w, ratio_h = 1, 1
    else:
        ratio_w, ratio_h = parsed
    if ratio_w >= ratio_h:
        width = max_extent
        height = round_half_away_from_zero(max_extent * ratio_h / ratio_w)
        return width, height
    height = max_extent
    width = round_half_away_from_zero(max_extent * ratio_w / ratio_h)
    return width, height


def _is_omitted(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip() == ""


def _coerce_extent(value: int | float | str) -> int:
    if isinstance(value, bool):
        raise ValidationError(_MSG_EXTENT_WHOLE, field="max_extent")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValidationError(_MSG_EXTENT_WHOLE, field="max_extent")
        return int(value)
    text = value.strip()
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    try:
        number = float(text)
    except ValueError as exc:
        raise ValidationError(_MSG_EXTENT_WHOLE, field="max_extent") from exc
    if not math.isfinite(number) or not number.is_integer():
        raise ValidationError(_MSG_EXTENT_WHOLE, field="max_extent")
    return int(number)


def normalize_size_pair(
    aspect_ratio: str | None,
    max_extent: int | float | str | None,
) -> tuple[str, int] | None:
    """Return a normalized pair, or ``None`` when both parts are omitted.

    A blank string is omitted. ``auto`` is lowercased. A whole-number float
    such as ``1024.0`` becomes an ``int``.

    Raises:
        ValidationError: One part is set and the other is omitted, the extent
            is outside 1024 through 2048, or the aspect token is illegal.
    """
    aspect_omitted = _is_omitted(aspect_ratio)
    extent_omitted = _is_omitted(max_extent)
    if aspect_omitted and extent_omitted:
        return None
    if aspect_omitted:
        raise ValidationError(_MSG_ASPECT_REQUIRED, field="aspect_ratio")
    if extent_omitted:
        raise ValidationError(_MSG_EXTENT_REQUIRED, field="max_extent")

    assert aspect_ratio is not None
    assert max_extent is not None
    extent = _coerce_extent(max_extent)
    if extent < MIN_OUTPUT_EXTENT or extent > MAX_OUTPUT_EXTENT:
        raise ValidationError(_MSG_EXTENT_RANGE, field="max_extent")

    parsed = parse_aspect_ratio(aspect_ratio)
    if parsed is None:
        return AUTO_ASPECT_TOKEN, extent
    width, height = parsed
    return f"{width}:{height}", extent


def _scale_long_side(image: Image.Image, max_extent: int) -> Image.Image:
    """Scale so the longer side equals ``max_extent``. Do not crop."""
    src_w, src_h = image.size
    long_side = src_w if src_w >= src_h else src_h
    if long_side == max_extent:
        return image.copy()
    if src_w >= src_h:
        new_w = max_extent
        new_h = round_half_away_from_zero(src_h * max_extent / src_w)
    else:
        new_h = max_extent
        new_w = round_half_away_from_zero(src_w * max_extent / src_h)
    return image.resize((new_w, new_h), Image.Resampling.LANCZOS)


def _center_crop_to_ratio(image: Image.Image, ratio_w: int, ratio_h: int) -> Image.Image:
    """Crop the axis that is too long. The window stays centered."""
    src_w, src_h = image.size
    if src_w * ratio_h > src_h * ratio_w:
        crop_h = src_h
        crop_w = (src_h * ratio_w) // ratio_h
    else:
        crop_w = src_w
        crop_h = (src_w * ratio_h) // ratio_w
    crop_w = max(crop_w, 1)
    crop_h = max(crop_h, 1)
    left = (src_w - crop_w) // 2
    top = (src_h - crop_h) // 2
    return image.crop((left, top, left + crop_w, top + crop_h))


def fit_image(image: Image.Image, aspect_ratio: str, max_extent: int) -> Image.Image:
    """Fit ``image`` to the requested pair. Keep the image mode.

    ``auto`` scales the longer side and does not crop. Any other ratio is
    center-cropped, then resized to :func:`ideal_pixel_size` with Lanczos.
    The short side is not clamped to ``MIN_OUTPUT_EXTENT``.
    """
    parsed = parse_aspect_ratio(aspect_ratio)
    if parsed is None:
        return _scale_long_side(image, max_extent)
    cropped = _center_crop_to_ratio(image, parsed[0], parsed[1])
    target = ideal_pixel_size(aspect_ratio, max_extent)
    if cropped.size == target:
        return cropped
    return cropped.resize(target, Image.Resampling.LANCZOS)
