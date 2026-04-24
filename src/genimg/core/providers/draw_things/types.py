"""Typed catalog records for Draw Things Echo metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelInfo:
    file: str
    name: str = ""
    version: str = ""
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LoraInfo:
    file: str
    name: str = ""
    version: str = ""
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ControlNetInfo:
    file: str
    name: str = ""
    version: str = ""
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TextualInversionInfo:
    file: str
    keyword: str = ""
    name: str = ""
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UpscalerInfo:
    """Upscalers are a generic JSON array in MetadataOverride; keep name/file when present."""

    name: str = ""
    file: str = ""
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ZooCatalog:
    models: tuple[ModelInfo, ...]
    loras: tuple[LoraInfo, ...]
    control_nets: tuple[ControlNetInfo, ...]
    textual_inversions: tuple[TextualInversionInfo, ...]
    upscalers: tuple[UpscalerInfo, ...]
