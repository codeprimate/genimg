"""
Load prompt templates from the bundled prompts.yaml file.

Prompts are defined in src/genimg/prompts.yaml and loaded once per process.
Add new prompt keys there and access them via get_prompt() or specific getters.
"""

import importlib.resources
from typing import Any

import yaml

# Module-level cache for parsed prompts
_prompts_data: dict[str, Any] | None = None


def _load_prompts() -> dict[str, Any]:
    """Load and parse prompts.yaml from the package. Cached after first call."""
    global _prompts_data
    if _prompts_data is not None:
        return _prompts_data
    try:
        with (
            importlib.resources.files("genimg").joinpath("prompts.yaml").open(encoding="utf-8") as f
        ):
            raw = f.read()
    except FileNotFoundError:
        _prompts_data = {}
        return _prompts_data
    _prompts_data = yaml.safe_load(raw) or {}
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
        The template string. Uses a built-in fallback if prompts.yaml is missing
        or the key is not present.
    """
    template = get_prompt("optimization", "template")
    if template and "{reference_image_instruction}" in template:
        return template
    # Fallback: visual scene architect (matches reference genimg_gradio_v3 behavior)
    return """You are a visual scene architect specializing in converting casual scene descriptions into precise, structured image generation prompts.
When given a user's scene description, rewrite it using this framework in an outline format:

Scene Setup: Establish location, time, lighting conditions, and capture medium (photography style, camera type, or artistic medium)
Camera Position and Framing: Specify exact camera placement, angle, lens characteristics, and what portions of subjects are visible from this vantage point

Subject Positions: List subjects and their positions in the scene. Detail each subject's location relative to camera and other subjects. Describe what parts are visible and from what angle. Include physical descriptions and attire.
Key Props: List significant objects and their positions in the scene

Action/Context: Describe what is happening, body language, interactions, or emotional tone
Technical Specs: Define visual aesthetic, quality characteristics, depth of field, lighting properties, and medium-specific attributes

Key principles:
- Resolve spatial ambiguities by explicitly stating what the camera sees and doesn't see
- Clarify relative positions using directional language (foreground/background, left/right, above/below)
- Specify viewing angles for each subject (frontal, profile, rear, elevated, etc.)
- Include relevant technical or stylistic constraints
- Remove redundancy while preserving essential details
- Preserve the information in the original prompt as best as possible

Transform the user's description into a clear, unambiguous prompt that any image generation system could interpret consistently.
{reference_image_instruction}

Output ONLY the improved prompt. Do not include explanations, prefixes, or markdown formatting.
Just output the optimized prompt text directly, following the framework outlined above."""
