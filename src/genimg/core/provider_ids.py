"""Canonical provider identifiers for image generation providers.

This module is intentionally stdlib-only so both ``config`` and ``providers``
can import from it without creating circular imports.
"""

from typing import Final

PROVIDER_OPENROUTER: Final[str] = "openrouter"
PROVIDER_OLLAMA: Final[str] = "ollama"
PROVIDER_DRAW_THINGS: Final[str] = "draw_things"

KNOWN_IMAGE_PROVIDER_IDS: Final[tuple[str, ...]] = (
    PROVIDER_OPENROUTER,
    PROVIDER_OLLAMA,
    PROVIDER_DRAW_THINGS,
)


def known_image_provider_ids() -> tuple[str, ...]:
    """Return the canonical tuple of known image provider identifiers."""
    return KNOWN_IMAGE_PROVIDER_IDS
