"""Decode Echo MetadataOverride into typed :class:`ZooCatalog`."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from genimg.contrib.draw_things_poc.types import (
    ControlNetInfo,
    LoraInfo,
    ModelInfo,
    TextualInversionInfo,
    UpscalerInfo,
    ZooCatalog,
)

# JSON object keys (aligned with dt-grpc-ts override.ts); used only in this module.
_JSON_KEY_FILE: str = "file"
_JSON_KEY_NAME: str = "name"
_JSON_KEY_VERSION: str = "version"
_JSON_KEY_PREFIX: str = "prefix"
_JSON_KEY_KEYWORD: str = "keyword"


def _split_known(
    row: Mapping[str, Any],
    known: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (known_subset, extras) for stable fields + forward-compat."""
    ks = {k: row[k] for k in known if k in row}
    extras = {k: v for k, v in row.items() if k not in known}
    return ks, extras


def _parse_models(raw: list[Any]) -> tuple[ModelInfo, ...]:
    out: list[ModelInfo] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = cast(dict[str, Any], item)
        ks, extras = _split_known(
            row,
            (_JSON_KEY_FILE, _JSON_KEY_NAME, _JSON_KEY_VERSION, _JSON_KEY_PREFIX),
        )
        out.append(
            ModelInfo(
                file=str(ks.get(_JSON_KEY_FILE, "")),
                name=str(ks.get(_JSON_KEY_NAME, "")),
                version=str(ks.get(_JSON_KEY_VERSION, "")),
                extras=extras,
            )
        )
    return tuple(out)


def _parse_loras(raw: list[Any]) -> tuple[LoraInfo, ...]:
    out: list[LoraInfo] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = cast(dict[str, Any], item)
        ks, extras = _split_known(
            row,
            (_JSON_KEY_FILE, _JSON_KEY_NAME, _JSON_KEY_VERSION, _JSON_KEY_PREFIX),
        )
        out.append(
            LoraInfo(
                file=str(ks.get(_JSON_KEY_FILE, "")),
                name=str(ks.get(_JSON_KEY_NAME, "")),
                version=str(ks.get(_JSON_KEY_VERSION, "")),
                extras=extras,
            )
        )
    return tuple(out)


def _parse_control_nets(raw: list[Any]) -> tuple[ControlNetInfo, ...]:
    out: list[ControlNetInfo] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = cast(dict[str, Any], item)
        ks, extras = _split_known(
            row,
            (_JSON_KEY_FILE, _JSON_KEY_NAME, _JSON_KEY_VERSION),
        )
        out.append(
            ControlNetInfo(
                file=str(ks.get(_JSON_KEY_FILE, "")),
                name=str(ks.get(_JSON_KEY_NAME, "")),
                version=str(ks.get(_JSON_KEY_VERSION, "")),
                extras=extras,
            )
        )
    return tuple(out)


def _parse_textual_inversions(raw: list[Any]) -> tuple[TextualInversionInfo, ...]:
    out: list[TextualInversionInfo] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = cast(dict[str, Any], item)
        ks, extras = _split_known(
            row,
            (_JSON_KEY_FILE, _JSON_KEY_NAME, _JSON_KEY_VERSION, _JSON_KEY_KEYWORD),
        )
        out.append(
            TextualInversionInfo(
                file=str(ks.get(_JSON_KEY_FILE, "")),
                keyword=str(ks.get(_JSON_KEY_KEYWORD, "")),
                name=str(ks.get(_JSON_KEY_NAME, "")),
                extras=extras,
            )
        )
    return tuple(out)


def _parse_upscalers(raw: list[Any]) -> tuple[UpscalerInfo, ...]:
    out: list[UpscalerInfo] = []
    for item in raw:
        if isinstance(item, str):
            out.append(UpscalerInfo(name=item))
            continue
        if not isinstance(item, dict):
            out.append(UpscalerInfo(extras={"value": item}))
            continue
        row = cast(dict[str, Any], item)
        ks, extras = _split_known(row, (_JSON_KEY_FILE, _JSON_KEY_NAME))
        out.append(
            UpscalerInfo(
                name=str(ks.get(_JSON_KEY_NAME, "")),
                file=str(ks.get(_JSON_KEY_FILE, "")),
                extras=extras,
            )
        )
    return tuple(out)


def _decode_json_bytes(buf: bytes) -> list[Any]:
    if not buf:
        return []
    text = buf.decode("utf-8")
    data = json.loads(text)
    if not isinstance(data, list):
        return []
    return data


def decode_metadata_override(override: Any) -> ZooCatalog:
    """Decode a protobuf ``MetadataOverride`` (or compatible object with ``models`` bytes fields)."""
    models_b = getattr(override, "models", b"") or b""
    loras_b = getattr(override, "loras", b"") or b""
    cn_b = getattr(override, "controlNets", b"") or b""
    ti_b = getattr(override, "textualInversions", b"") or b""
    up_b = getattr(override, "upscalers", b"") or b""

    return ZooCatalog(
        models=_parse_models(_decode_json_bytes(bytes(models_b))),
        loras=_parse_loras(_decode_json_bytes(bytes(loras_b))),
        control_nets=_parse_control_nets(_decode_json_bytes(bytes(cn_b))),
        textual_inversions=_parse_textual_inversions(_decode_json_bytes(bytes(ti_b))),
        upscalers=_parse_upscalers(_decode_json_bytes(bytes(up_b))),
    )


def empty_zoo_catalog() -> ZooCatalog:
    return ZooCatalog(
        models=(),
        loras=(),
        control_nets=(),
        textual_inversions=(),
        upscalers=(),
    )
