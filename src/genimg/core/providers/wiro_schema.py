"""Wiro model schema parsing and run payload construction."""

from __future__ import annotations

import base64
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from genimg.core.output_size import (
    AUTO_ASPECT_TOKEN,
    MATCH_INPUT_IMAGE_TEXT,
    MAX_OUTPUT_EXTENT,
    MIN_OUTPUT_EXTENT,
    NOMINAL_K_PIXELS,
    WIRO_SIZE_FIELD_IDS,
    ideal_pixel_size,
    parse_aspect_ratio,
    round_half_away_from_zero,
)
from genimg.utils.exceptions import ValidationError

FILE_PARAM_TYPES = frozenset({"fileinput", "multifileinput", "combinefileinput"})

_FRAME_COLON_RE = re.compile(r"(\d+(?:\.\d+)?)([kK])\s*:\s*(\d+)\s*[x×]\s*(\d+)")
_FRAME_PAREN_RE = re.compile(r"\((\d+(?:\.\d+)?)([kK])\)\s*(\d+)\s*[x×]\s*(\d+)")
_NOMINAL_K_RE = re.compile(r"(?i)^(\d+(?:\.\d+)?)k$")
_MSG_PARTIAL_SIZE = "aspect_ratio and max_extent must be set together."


class ContentMode(str, Enum):
    """How to send the Run request body."""

    JSON = "json"
    MULTIPART = "multipart"


@dataclass(frozen=True)
class FileSlot:
    """One mappable reference-image target in a model schema."""

    param_id: str
    param_type: str


@dataclass(frozen=True)
class ModelRunPlan:
    """Resolved mapping from genimg inputs to Wiro Run parameters."""

    prompt_field_id: str
    file_slots: tuple[FileSlot, ...]
    content_mode: ContentMode
    json_fields: dict[str, str]
    multipart_text_fields: dict[str, str]
    multipart_files: tuple[tuple[str, str, bytes, str], ...]
    # multipart_files: (field_name, filename, content_bytes, content_type)


def parse_model_slugs(model: str) -> tuple[str, str]:
    """Split ``owner/model`` into Wiro slugowner and slugproject."""
    stripped = (model or "").strip()
    if not stripped or "/" not in stripped:
        raise ValidationError(
            f"Wiro model must be in owner/model format, got {model!r}.",
            field="model",
        )
    owner, project = stripped.split("/", 1)
    owner = owner.strip()
    project = project.strip()
    if not owner or not project:
        raise ValidationError(
            f"Wiro model must be in owner/model format, got {model!r}.",
            field="model",
        )
    return owner, project


def flatten_param_items(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Return flattened parameter items from a Tool/Detail response."""
    tool = schema.get("tool")
    if not isinstance(tool, list) or not tool:
        return []
    first = tool[0]
    if not isinstance(first, dict):
        return []
    parameters = first.get("parameters")
    if not isinstance(parameters, list):
        return []
    items: list[dict[str, Any]] = []
    for group in parameters:
        if not isinstance(group, dict):
            continue
        group_items = group.get("items")
        if isinstance(group_items, list):
            items.extend(i for i in group_items if isinstance(i, dict))
    return items


def model_has_file_inputs(schema: dict[str, Any]) -> bool:
    """Return True if the model schema declares any file input parameters."""
    return any((item.get("type") or "") in FILE_PARAM_TYPES for item in flatten_param_items(schema))


def _resolve_prompt_field_id(items: list[dict[str, Any]]) -> str:
    for item in items:
        if item.get("id") == "prompt" and item.get("type") in ("textarea", "text"):
            return "prompt"
    for item in items:
        if item.get("type") == "textarea" and item.get("required"):
            param_id = item.get("id")
            if isinstance(param_id, str) and param_id:
                return param_id
    for item in items:
        if item.get("type") == "textarea":
            param_id = item.get("id")
            if isinstance(param_id, str) and param_id:
                return param_id
    return "prompt"


def _file_slots_from_items(items: list[dict[str, Any]]) -> tuple[FileSlot, ...]:
    slots: list[FileSlot] = []
    for item in items:
        param_type = item.get("type")
        if param_type not in FILE_PARAM_TYPES:
            continue
        param_id = item.get("id")
        if isinstance(param_id, str) and param_id:
            slots.append(FileSlot(param_id=param_id, param_type=str(param_type)))
    return tuple(slots)


def _decode_reference_images(reference_images_b64: list[str] | None) -> list[bytes]:
    if not reference_images_b64:
        return []
    decoded: list[bytes] = []
    for ref_b64 in reference_images_b64:
        if not ref_b64:
            continue
        try:
            decoded.append(base64.b64decode(ref_b64))
        except ValueError as e:
            raise ValidationError(
                f"Invalid base64 reference image: {e}",
                field="reference_image",
            ) from e
    return decoded


def _max_reference_count(slots: tuple[FileSlot, ...]) -> int:
    if not slots:
        return 0
    count = 0
    for slot in slots:
        if slot.param_type == "combinefileinput":
            return max(count + 1, 8)
        count += 1
    return count


def _default_value_for_required_param(item: dict[str, Any]) -> str | None:
    """Return a sensible default string for a required schema parameter."""
    param_type = item.get("type")
    if param_type == "select":
        options = item.get("options")
        if isinstance(options, list) and options:
            first = options[0]
            if isinstance(first, dict) and "value" in first:
                return str(first["value"])
        return None
    if param_type == "number":
        return "1"
    if param_type in ("text", "textarea"):
        return ""
    if param_type == "checkbox":
        return "false"
    return None


def _select_option_values(item: dict[str, Any]) -> frozenset[str]:
    """Return the ``value`` strings of a select parameter.

    The size mapper does not call this helper. It remains so a later cleanup
    can delete it in one place.
    """
    options = item.get("options")
    if not isinstance(options, list):
        return frozenset()
    values: set[str] = set()
    for option in options:
        if isinstance(option, dict) and "value" in option:
            values.add(str(option["value"]))
    return frozenset(values)


def _items_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for item in items:
        param_id = item.get("id")
        if isinstance(param_id, str) and param_id:
            found[param_id] = item
    return found


def _positive_bound(value: object) -> int | None:
    """Return a positive integer bound. Ignore ``0``, blanks, and bools."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer() and value > 0:
            return int(value)
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            number = int(text)
            return number if number > 0 else None
    return None


def _defaultvalue_text(item: dict[str, Any]) -> str | None:
    raw = item.get("defaultvalue")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _option_dicts(item: dict[str, Any]) -> list[dict[str, Any]]:
    options = item.get("options")
    if not isinstance(options, list):
        return []
    return [option for option in options if isinstance(option, dict)]


def _option_value_text(option: dict[str, Any]) -> str:
    if "value" not in option or option.get("value") is None:
        return ""
    return str(option["value"])


def _option_label_text(option: dict[str, Any]) -> str:
    text = option.get("text")
    if isinstance(text, str):
        return text
    return ""


def _same_token(left: str, right: str) -> bool:
    return left.strip().lower() == right.strip().lower()


def _parse_ratio_token(token: str) -> tuple[int, int] | None:
    try:
        return parse_aspect_ratio(token)
    except ValidationError:
        return None


def _numeric_option_ratio(option: dict[str, Any]) -> tuple[int, int] | None:
    """Read ``W:H`` from ``value``, or from ``text`` when the value is not a ratio."""
    value = _option_value_text(option).strip()
    parsed = _parse_ratio_token(value)
    if parsed is not None:
        return parsed
    return _parse_ratio_token(_option_label_text(option).strip())


def _copy_size_defaults(
    items_by_id: dict[str, dict[str, Any]],
    fields: dict[str, str],
) -> None:
    """Copy in-range ``defaultvalue`` strings for the four size ids."""
    for param_id in ("aspectRatio", "resolution"):
        item = items_by_id.get(param_id)
        if item is None:
            continue
        text = _defaultvalue_text(item)
        if text is not None:
            fields[param_id] = text

    for param_id in ("width", "height"):
        item = items_by_id.get(param_id)
        if item is None:
            continue
        text = _defaultvalue_text(item)
        if text is None:
            continue
        if _pixel_default_in_range(item, text):
            fields[param_id] = text


def _pixel_default_in_range(item: dict[str, Any], text: str) -> bool:
    minimum = _positive_bound(item.get("minvalue"))
    maximum = _positive_bound(item.get("maxvalue"))
    if minimum is None and maximum is None:
        return True
    number = _positive_bound(text)
    if number is None:
        return False
    if minimum is not None and number < minimum:
        return False
    return maximum is None or number <= maximum


def _pixel_pair_breaks(
    width: int,
    height: int,
    w_min: int | None,
    w_max: int | None,
    h_min: int | None,
    h_max: int | None,
) -> bool:
    long_side = width if width >= height else height
    if long_side < MIN_OUTPUT_EXTENT or long_side > MAX_OUTPUT_EXTENT:
        return True
    if w_min is not None and width < w_min:
        return True
    if w_max is not None and width > w_max:
        return True
    if h_min is not None and height < h_min:
        return True
    return h_max is not None and height > h_max


def _scale_closest_to_one(lower: float, upper: float) -> float | None:
    if lower > upper:
        return None
    if lower <= 1.0 <= upper:
        return 1.0
    if upper < 1.0:
        return upper
    return lower


def _pixel_fallback(
    width: int,
    height: int,
    w_min: int | None,
    w_max: int | None,
    h_min: int | None,
    h_max: int | None,
) -> tuple[int, int] | None:
    """Schema max on the long side and schema min on the short side."""
    if width >= height:
        long_max, short_min = w_max, h_min
        long_is_width = True
    else:
        long_max, short_min = h_max, w_min
        long_is_width = False
    if long_max is None or short_min is None:
        return None
    if long_is_width:
        return long_max, short_min
    return short_min, long_max


def _fit_pixel_pair(
    width: int,
    height: int,
    width_item: dict[str, Any],
    height_item: dict[str, Any],
) -> tuple[int, int]:
    w_min = _positive_bound(width_item.get("minvalue"))
    w_max = _positive_bound(width_item.get("maxvalue"))
    h_min = _positive_bound(height_item.get("minvalue"))
    h_max = _positive_bound(height_item.get("maxvalue"))
    if width <= 0 or height <= 0:
        fallback = _pixel_fallback(width, height, w_min, w_max, h_min, h_max)
        return fallback if fallback is not None else (width, height)
    if not _pixel_pair_breaks(width, height, w_min, w_max, h_min, h_max):
        return width, height

    long_side = width if width >= height else height
    lower = MIN_OUTPUT_EXTENT / long_side
    upper = MAX_OUTPUT_EXTENT / long_side
    if w_max is not None:
        upper = min(upper, w_max / width)
    if h_max is not None:
        upper = min(upper, h_max / height)
    if w_min is not None:
        lower = max(lower, w_min / width)
    if h_min is not None:
        lower = max(lower, h_min / height)

    scale = _scale_closest_to_one(lower, upper)
    if scale is not None:
        scaled = (
            round_half_away_from_zero(width * scale),
            round_half_away_from_zero(height * scale),
        )
        if not _pixel_pair_breaks(scaled[0], scaled[1], w_min, w_max, h_min, h_max):
            return scaled

    fallback = _pixel_fallback(width, height, w_min, w_max, h_min, h_max)
    if fallback is not None:
        return fallback
    return width, height


def _apply_pixel_size(
    items_by_id: dict[str, dict[str, Any]],
    fields: dict[str, str],
    aspect_ratio: str,
    max_extent: int,
) -> None:
    width_item = items_by_id["width"]
    height_item = items_by_id["height"]
    width, height = ideal_pixel_size(aspect_ratio, max_extent)
    fitted_w, fitted_h = _fit_pixel_pair(width, height, width_item, height_item)
    fields.pop("aspectRatio", None)
    fields.pop("resolution", None)
    fields["width"] = str(fitted_w)
    fields["height"] = str(fitted_h)


def resolution_frames(text: str) -> list[tuple[str, int]]:
    """Return ``(tier_token, long_side)`` for Seedream and Nano Banana frame text.

    Colon form is ``2k: 2560x1440``. Parenthesis form is ``(1K)1376x768``.
    ``x`` and ``×`` both count. Results follow the text order.
    """
    found: list[tuple[int, str, int]] = []
    for pattern in (_FRAME_COLON_RE, _FRAME_PAREN_RE):
        for match in pattern.finditer(text):
            tier = f"{match.group(1)}{match.group(2)}"
            long_side = max(int(match.group(3)), int(match.group(4)))
            found.append((match.start(), tier, long_side))
    found.sort(key=lambda item: item[0])
    return [(tier, long_side) for _, tier, long_side in found]


def _stored_value_for_token(options: list[dict[str, Any]], token: str) -> str | None:
    for option in options:
        if _same_token(_option_value_text(option), token):
            return _option_value_text(option)
    return None


def _closest_labeled_side(
    candidates: list[tuple[str, int, int]],
    max_extent: int,
) -> str | None:
    """Pick a stored value. Each row is ``(stored_value, long_side, order)``."""
    best: tuple[int, int, int, str] | None = None
    for stored, long_side, order in candidates:
        distance = abs(long_side - max_extent)
        within = 0 if long_side <= max_extent else 1
        rank = (distance, within, order, stored)
        if best is None or rank < best:
            best = rank
    if best is None:
        return None
    return best[3]


def _resolution_from_frames(
    options: list[dict[str, Any]],
    frames: list[tuple[str, int]],
    max_extent: int,
) -> str | None:
    candidates: list[tuple[str, int, int]] = []
    for order, (tier, long_side) in enumerate(frames):
        stored = _stored_value_for_token(options, tier)
        if stored is None:
            continue
        candidates.append((stored, long_side, order))
    return _closest_labeled_side(candidates, max_extent)


def _resolution_from_nominal_k(
    options: list[dict[str, Any]],
    max_extent: int,
) -> str | None:
    candidates: list[tuple[str, int, int]] = []
    for order, option in enumerate(options):
        raw = _option_value_text(option)
        match = _NOMINAL_K_RE.fullmatch(raw.strip())
        if match is None:
            continue
        long_side = round_half_away_from_zero(float(match.group(1)) * NOMINAL_K_PIXELS)
        candidates.append((raw, long_side, order))
    return _closest_labeled_side(candidates, max_extent)


def _resolution_value(
    resolution_item: dict[str, Any] | None,
    aspect_option: dict[str, Any] | None,
    max_extent: int,
) -> str | None:
    if resolution_item is None or resolution_item.get("type") != "select":
        return None
    if aspect_option is None:
        return None
    options = _option_dicts(resolution_item)
    frames = resolution_frames(_option_label_text(aspect_option))
    if frames:
        return _resolution_from_frames(options, frames, max_extent)
    return _resolution_from_nominal_k(options, max_extent)


def _match_auto_option(options: list[dict[str, Any]]) -> dict[str, Any] | None:
    for option in options:
        if _same_token(_option_value_text(option), AUTO_ASPECT_TOKEN):
            return option
    for option in options:
        if _same_token(_option_label_text(option), AUTO_ASPECT_TOKEN):
            return option
    for option in options:
        if _same_token(_option_label_text(option), MATCH_INPUT_IMAGE_TEXT):
            return option
    return None


def _closest_aspect_option(
    options: list[dict[str, Any]],
    token: str,
) -> dict[str, Any] | None:
    parsed = _parse_ratio_token(token)
    if parsed is None:
        return None
    caller_q = parsed[0] / parsed[1]
    best: tuple[float, int, dict[str, Any]] | None = None
    for index, option in enumerate(options):
        ratio = _numeric_option_ratio(option)
        if ratio is None:
            continue
        distance = abs(caller_q - (ratio[0] / ratio[1]))
        rank = (distance, index, option)
        if best is None or rank < best:
            best = rank
    if best is None:
        return None
    return best[2]


def _select_aspect(
    item: dict[str, Any],
    token: str,
) -> tuple[str, dict[str, Any] | None]:
    """Return the aspect value to send and the option it came from, if any."""
    options = _option_dicts(item)
    if _same_token(token, AUTO_ASPECT_TOKEN):
        matched = _match_auto_option(options)
        if matched is not None:
            return _option_value_text(matched), matched
        return _aspect_fallback(item, options)

    for option in options:
        if _same_token(_option_value_text(option), token):
            return _option_value_text(option), option

    closest = _closest_aspect_option(options, token)
    if closest is not None:
        return _option_value_text(closest), closest
    return _aspect_fallback(item, options)


def _aspect_fallback(
    item: dict[str, Any],
    options: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None]:
    default = _defaultvalue_text(item)
    if default is not None:
        return default, None
    if options:
        return _option_value_text(options[0]), options[0]
    return "", None


def _apply_ratio_size(
    items_by_id: dict[str, dict[str, Any]],
    fields: dict[str, str],
    aspect_ratio: str,
    max_extent: int,
) -> None:
    aspect_item = items_by_id["aspectRatio"]
    sent_value, aspect_option = _select_aspect(aspect_item, aspect_ratio)
    fields.pop("width", None)
    fields.pop("height", None)
    fields["aspectRatio"] = sent_value
    resolution = _resolution_value(items_by_id.get("resolution"), aspect_option, max_extent)
    if resolution is None:
        fields.pop("resolution", None)
    else:
        fields["resolution"] = resolution


def apply_size_fields(
    items: list[dict[str, Any]],
    fields: dict[str, str],
    aspect_ratio: str | None,
    max_extent: int | None,
) -> dict[str, str]:
    """Write the four size ids for one Run body.

    A set pair uses the pixel adapter or the ratio adapter and does not copy
    ``defaultvalue``. An omitted pair copies non-empty in-range
    ``defaultvalue`` strings only.
    """
    updated = dict(fields)
    items_by_id = _items_by_id(items)
    if aspect_ratio is None and max_extent is None:
        _copy_size_defaults(items_by_id, updated)
        return updated
    if aspect_ratio is None or max_extent is None:
        missing = "aspect_ratio" if aspect_ratio is None else "max_extent"
        raise ValidationError(_MSG_PARTIAL_SIZE, field=missing)

    aspect_item = items_by_id.get("aspectRatio")
    if aspect_item is not None and aspect_item.get("type") == "select":
        _apply_ratio_size(items_by_id, updated, aspect_ratio, max_extent)
        return updated
    if "width" in items_by_id and "height" in items_by_id:
        _apply_pixel_size(items_by_id, updated, aspect_ratio, max_extent)
    return updated


def aspect_choices_from_schema(schema: dict[str, Any]) -> list[tuple[str, str]] | None:
    """Return ``(label, submit_value)`` rows for an ``aspectRatio`` select.

    Returns ``None`` when the schema has no ``aspectRatio`` select. A blank
    ``auto`` or ``Match Input Image`` value submits the token ``auto``.
    """
    aspect_item: dict[str, Any] | None = None
    for item in flatten_param_items(schema):
        if item.get("id") == "aspectRatio" and item.get("type") == "select":
            aspect_item = item
            break
    if aspect_item is None:
        return None

    rows: list[tuple[str, str]] = []
    for option in _option_dicts(aspect_item):
        value = _option_value_text(option)
        text = _option_label_text(option)
        label = text.strip() if text.strip() else value.strip()
        if value.strip():
            submit = value.strip()
        elif _same_token(text, AUTO_ASPECT_TOKEN) or _same_token(text, MATCH_INPUT_IMAGE_TEXT):
            submit = AUTO_ASPECT_TOKEN
        else:
            continue
        if not label:
            label = submit
        rows.append((label, submit))
    return rows


def _static_schema_fields(
    items: list[dict[str, Any]],
    *,
    prompt_field_id: str,
    file_slot_ids: frozenset[str],
) -> dict[str, str]:
    """Build non-prompt, non-file Run fields from schema defaults and required params."""
    fields: dict[str, str] = {}
    for item in items:
        param_id = item.get("id")
        if not isinstance(param_id, str) or not param_id:
            continue
        if param_id == prompt_field_id or param_id in file_slot_ids:
            continue
        if param_id in WIRO_SIZE_FIELD_IDS:
            continue

        explicit_default = item.get("default")
        if explicit_default is not None and str(explicit_default).strip():
            fields[param_id] = str(explicit_default)
            continue

        if not item.get("required"):
            continue

        default_value = _default_value_for_required_param(item)
        if default_value is not None:
            fields[param_id] = default_value
    return fields


def _assign_refs_to_slots(
    slots: tuple[FileSlot, ...],
    refs: list[bytes],
) -> list[tuple[FileSlot, bytes]]:
    if not refs:
        return []
    if not slots:
        raise ValidationError(
            "Reference images were provided but the model accepts no file inputs.",
            field="reference_image",
        )

    assignments: list[tuple[FileSlot, bytes]] = []
    ref_idx = 0
    slot_idx = 0
    while ref_idx < len(refs):
        if slot_idx >= len(slots):
            raise ValidationError(
                f"Too many reference images for model (supports up to {len(slots)} file inputs).",
                field="reference_image",
            )
        slot = slots[slot_idx]
        if slot.param_type == "combinefileinput":
            while ref_idx < len(refs):
                assignments.append((slot, refs[ref_idx]))
                ref_idx += 1
            break
        assignments.append((slot, refs[ref_idx]))
        ref_idx += 1
        slot_idx += 1
    return assignments


def build_run_plan(
    schema: dict[str, Any],
    *,
    prompt: str,
    reference_images_b64: list[str] | None,
    model_label: str = "",
    aspect_ratio: str | None = None,
    max_extent: int | None = None,
) -> ModelRunPlan:
    """Build JSON or multipart Run payload from Tool/Detail schema.

    ``aspect_ratio`` and ``max_extent`` are both set or both omitted. A set
    pair is mapped onto the schema. An omitted pair copies size
    ``defaultvalue`` strings and does not invent a square size.
    """
    items = flatten_param_items(schema)
    prompt_field_id = _resolve_prompt_field_id(items)
    file_slots = _file_slots_from_items(items)
    refs = _decode_reference_images(reference_images_b64)

    if refs and not file_slots:
        label = model_label or "model"
        raise ValidationError(
            f"Reference images are not supported for Wiro model {label!r} (no file inputs in schema).",
            field="reference_image",
        )

    max_refs = _max_reference_count(file_slots)
    if len(refs) > max_refs and file_slots:
        non_combine = [s for s in file_slots if s.param_type != "combinefileinput"]
        limit = len(non_combine) if non_combine else max_refs
        raise ValidationError(
            f"Too many reference images for model (supports up to {limit}).",
            field="reference_image",
        )

    assignments = _assign_refs_to_slots(file_slots, refs)
    file_slot_ids = frozenset(slot.param_id for slot in file_slots)
    static_fields = apply_size_fields(
        items,
        _static_schema_fields(
            items,
            prompt_field_id=prompt_field_id,
            file_slot_ids=file_slot_ids,
        ),
        aspect_ratio,
        max_extent,
    )

    if not assignments:
        return ModelRunPlan(
            prompt_field_id=prompt_field_id,
            file_slots=file_slots,
            content_mode=ContentMode.JSON,
            json_fields={**static_fields, prompt_field_id: prompt},
            multipart_text_fields={},
            multipart_files=(),
        )

    text_fields: dict[str, str] = {**static_fields, prompt_field_id: prompt}
    files: list[tuple[str, str, bytes, str]] = []
    for slot, ref_bytes in assignments:
        filename = f"{slot.param_id}.png"
        content_type = "image/png"
        if slot.param_type in ("fileinput", "multifileinput"):
            text_fields[f"{slot.param_id}Url"] = ""
            files.append((slot.param_id, filename, ref_bytes, content_type))
        else:
            files.append((slot.param_id, filename, ref_bytes, content_type))

    return ModelRunPlan(
        prompt_field_id=prompt_field_id,
        file_slots=file_slots,
        content_mode=ContentMode.MULTIPART,
        json_fields={},
        multipart_text_fields=text_fields,
        multipart_files=tuple(files),
    )


def detect_image_format(image_bytes: bytes) -> str:
    """Return a Pillow-friendly format name from image magic bytes."""
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes[:2] == b"\xff\xd8":
        return "jpeg"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "webp"
    return "png"
