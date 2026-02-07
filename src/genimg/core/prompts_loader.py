"""
Load prompt templates from the bundled prompts.yaml file.

Prompts are defined in src/genimg/prompts.yaml and loaded once per process.
Add new prompt keys there and access them via get_prompt() or specific getters.
"""

import importlib.resources
from typing import Any, Optional

import yaml

# Module-level cache for parsed prompts
_prompts_data: Optional[dict[str, Any]] = None


def _load_prompts() -> dict[str, Any]:
    """Load and parse prompts.yaml from the package. Cached after first call."""
    global _prompts_data
    if _prompts_data is not None:
        return _prompts_data
    try:
        with importlib.resources.files("genimg").joinpath("prompts.yaml").open(
            encoding="utf-8"
        ) as f:
            raw = f.read()
    except FileNotFoundError:
        _prompts_data = {}
        return _prompts_data
    _prompts_data = yaml.safe_load(raw) or {}
    return _prompts_data


def get_prompt(key: str, subkey: Optional[str] = None) -> Optional[str]:
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
    Return the optimization prompt template (must contain {original_prompt}).

    Returns:
        The template string. Uses a built-in fallback if prompts.yaml is missing
        or the key is not present.
    """
    template = get_prompt("optimization", "template")
    if template and "{original_prompt}" in template:
        return template
    # Fallback matching original hardcoded template
    return """You are a professional prompt engineer for AI image generation. Your task is to enhance the user's prompt to produce better, more detailed images.

User's original prompt:
{original_prompt}

Please enhance this prompt by:
1. Adding technical photography details (camera angle, lighting, composition) if applicable
2. Clarifying spatial relationships and scene layout
3. Specifying style and artistic qualities
4. Adding relevant details that match the intent
5. Structuring the information clearly

IMPORTANT: If the prompt mentions a reference image, preserve those instructions EXACTLY as written.

Return ONLY the enhanced prompt, without any explanations or meta-commentary."""
