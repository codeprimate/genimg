"""Wiro model schema parsing and run payload construction."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import Enum
from typing import Any

from genimg.utils.exceptions import ValidationError

FILE_PARAM_TYPES = frozenset({"fileinput", "multifileinput", "combinefileinput"})

# When a reference image is sent, Wiro models default aspectRatio to "auto" and inherit
# the input image ratio — often producing extreme outputs. Force 1:1 to match genimg defaults.
WIRO_REFERENCE_ASPECT_RATIO = "1:1"
WIRO_REFERENCE_SQUARE_SIZE = "1024"


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
    return any(
        (item.get("type") or "") in FILE_PARAM_TYPES for item in flatten_param_items(schema)
    )


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
    options = item.get("options")
    if not isinstance(options, list):
        return frozenset()
    values: set[str] = set()
    for option in options:
        if isinstance(option, dict) and "value" in option:
            values.add(str(option["value"]))
    return frozenset(values)


def _apply_reference_output_sizing(
    items: list[dict[str, Any]],
    fields: dict[str, str],
    *,
    has_reference: bool,
) -> dict[str, str]:
    """Pin output to square when reference images would otherwise inherit input ratio."""
    if not has_reference:
        return fields

    updated = dict(fields)
    param_by_id = {
        item.get("id"): item
        for item in items
        if isinstance(item.get("id"), str) and item.get("id")
    }

    aspect_item = param_by_id.get("aspectRatio")
    if aspect_item is not None and "aspectRatio" not in updated:
        if WIRO_REFERENCE_ASPECT_RATIO in _select_option_values(aspect_item):
            updated["aspectRatio"] = WIRO_REFERENCE_ASPECT_RATIO

    if "width" in param_by_id and "height" in param_by_id:
        if "width" not in updated:
            updated["width"] = WIRO_REFERENCE_SQUARE_SIZE
        if "height" not in updated:
            updated["height"] = WIRO_REFERENCE_SQUARE_SIZE

    return updated


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
) -> ModelRunPlan:
    """Build JSON or multipart Run payload from Tool/Detail schema."""
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
    static_fields = _apply_reference_output_sizing(
        items,
        _static_schema_fields(
            items,
            prompt_field_id=prompt_field_id,
            file_slot_ids=file_slot_ids,
        ),
        has_reference=bool(refs),
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
