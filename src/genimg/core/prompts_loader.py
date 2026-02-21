"""
Load prompt templates from the bundled prompts.yaml file.

Prompts are defined in src/genimg/prompts.yaml and loaded once per process.
Add new prompt keys there and access them via get_prompt() or specific getters.
"""

import importlib.resources
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError

from genimg.utils.exceptions import ConfigurationError

# Module-level cache for parsed prompts
_prompts_data: dict[str, Any] | None = None


class OptimizationPrompt(BaseModel):
    """Schema for optimization prompt configuration."""

    template: str = Field(..., min_length=1, description="Optimization template string")
    template_with_description: str | None = Field(
        default=None,
        description="Template when reference image description is used; must contain {reference_description}",
    )


class PromptsSchema(BaseModel):
    """Schema for prompts.yaml configuration file."""

    model_config = {"extra": "allow"}  # Allow additional keys for future expansion

    optimization: OptimizationPrompt


def _load_prompts() -> dict[str, Any]:
    """Load and parse prompts.yaml from the package. Cached after first call.

    Returns:
        Dictionary of prompt data.

    Raises:
        ConfigurationError: If YAML is missing, malformed, or fails validation.
    """
    global _prompts_data
    if _prompts_data is not None:
        return _prompts_data

    try:
        with (
            importlib.resources.files("genimg").joinpath("prompts.yaml").open(encoding="utf-8") as f
        ):
            raw = f.read()
    except FileNotFoundError as e:
        raise ConfigurationError(
            "prompts.yaml not found. This file is required and should be bundled with the package."
        ) from e

    # Parse YAML
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ConfigurationError(
            f"Failed to parse prompts.yaml: {e}. Check YAML syntax and formatting."
        ) from e

    if data is None:
        raise ConfigurationError(
            "prompts.yaml is empty. Expected configuration with 'optimization' section."
        )

    # Validate structure with Pydantic
    try:
        PromptsSchema(**data)
    except ValidationError as e:
        errors = "\n".join([f"  - {err['loc'][0]}: {err['msg']}" for err in e.errors()])
        raise ConfigurationError(
            f"Invalid prompts.yaml structure:\n{errors}\n"
            "Expected 'optimization' section with 'template' key."
        ) from e

    _prompts_data = data
    return _prompts_data


def get_prompt(key: str, subkey: str | None = None) -> str | None:
    """
    Get a prompt string from prompts.yaml.

    Args:
        key: Top-level key (e.g. "optimization").
        subkey: Optional subkey (e.g. "template") for nested value.

    Returns:
        The prompt string, or None if not found.
    """
    data = _load_prompts()
    value = data.get(key)
    if value is None:
        return None
    if subkey is not None:
        value = value.get(subkey) if isinstance(value, dict) else None
    return value if isinstance(value, str) else None


def get_optimization_template() -> str:
    """
    Return the optimization system prompt template (must contain {reference_image_instruction}).
    Caller appends "Original prompt: <prompt>\\n\\nImproved prompt:" to form the full message.

    Returns:
        The template string from prompts.yaml.

    Raises:
        ConfigurationError: If template is missing or invalid.
    """
    template = get_prompt("optimization", "template")
    if not template:
        raise ConfigurationError(
            "optimization.template not found in prompts.yaml. This key is required."
        )
    if "{reference_image_instruction}" not in template:
        raise ConfigurationError(
            "optimization.template must contain {reference_image_instruction} placeholder."
        )
    return template


def get_optimization_template_with_description() -> str:
    """
    Return the optimization template used when a reference image description is provided.
    Must contain {reference_description} placeholder.

    Returns:
        The template string from prompts.yaml (optimization.template_with_description).

    Raises:
        ConfigurationError: If template is missing or does not contain the placeholder.
    """
    template = get_prompt("optimization", "template_with_description")
    if not template:
        raise ConfigurationError(
            "optimization.template_with_description not found in prompts.yaml. "
            "Required when using description-based optimization."
        )
    if "{reference_description}" not in template:
        raise ConfigurationError(
            "optimization.template_with_description must contain {reference_description} placeholder."
        )
    return template
