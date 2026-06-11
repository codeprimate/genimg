"""
Load default model IDs and suggestion lists from the bundled models.yaml file.

Model defaults are defined in src/genimg/models.yaml and loaded once per process.
Config reads these values at import time; env vars override via Config.from_env().
"""

from __future__ import annotations

import importlib.resources
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from genimg.utils.exceptions import ConfigurationError

_models_data: dict[str, Any] | None = None


class ModelsSchema(BaseModel):
    """Schema for models.yaml configuration file."""

    default_image_model: str = Field(..., min_length=1)
    default_ollama_image_model: str = Field(..., min_length=1)
    default_optimization_model: str = Field(..., min_length=1)
    image_models: list[str] = Field(default_factory=list)


def _load_models() -> dict[str, Any]:
    """Load and parse models.yaml from the package. Cached after first call."""
    global _models_data
    if _models_data is not None:
        return _models_data

    try:
        with (
            importlib.resources.files("genimg").joinpath("models.yaml").open(encoding="utf-8") as f
        ):
            raw = f.read()
    except FileNotFoundError as e:
        raise ConfigurationError(
            "models.yaml not found. This file is required and should be bundled with the package."
        ) from e

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ConfigurationError(
            f"Failed to parse models.yaml: {e}. Check YAML syntax and formatting."
        ) from e

    if data is None:
        raise ConfigurationError(
            "models.yaml is empty. Expected default_* keys and optional model lists."
        )

    try:
        ModelsSchema(**data)
    except PydanticValidationError as e:
        errors = "\n".join([f"  - {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()])
        raise ConfigurationError(
            f"Invalid models.yaml structure:\n{errors}\n"
            "Expected default_image_model, default_ollama_image_model, "
            "and default_optimization_model keys."
        ) from e

    _models_data = data
    return _models_data


def default_image_model() -> str:
    """Default OpenRouter-style image model ID."""
    return str(_load_models()["default_image_model"])


def default_ollama_image_model() -> str:
    """Default Ollama image model ID."""
    return str(_load_models()["default_ollama_image_model"])


def default_optimization_model() -> str:
    """Default Ollama prompt optimization model ID."""
    return str(_load_models()["default_optimization_model"])


def image_models() -> list[str]:
    """OpenRouter image model suggestion list."""
    return list(_load_models().get("image_models") or [])


def merge_optimization_model_choices(
    *,
    default: str,
    installed: list[str],
) -> list[str]:
    """Merge default and installed Ollama models (default first, deduplicated)."""
    merged: list[str] = []
    seen: set[str] = set()
    for name in (default, *installed):
        stripped = name.strip() if isinstance(name, str) else ""
        if stripped and stripped not in seen:
            merged.append(stripped)
            seen.add(stripped)
    return merged
