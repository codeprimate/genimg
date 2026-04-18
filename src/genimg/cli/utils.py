"""
Utility functions for the CLI.

This module contains helper functions used by CLI commands,
such as path generation and exit code constants.
"""

import re
from datetime import datetime

from genimg.core.image_gen import CliImageFormat, cli_format_to_extension

# Exit codes (130 = common for SIGINT)
EXIT_SUCCESS = 0
EXIT_API_OR_NETWORK = 1
EXIT_VALIDATION_OR_CONFIG = 2
EXIT_CANCELLED = 130

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_CHARACTER_STEM_LEN = 80


def default_output_path(cli_format: CliImageFormat) -> str:
    """Return default path ``genimg_<YYYYMMDD>_<HHMMSS>.<ext>`` using CLI disk format."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = cli_format_to_extension(cli_format).lstrip(".")
    return f"genimg_{timestamp}.{ext}"


def _slug_title_for_character_filename(title: str) -> str:
    """Filesystem-safe stem from human title (may be empty if title has no usable chars)."""
    s = (title or "").strip()
    s = _CONTROL_CHARS_RE.sub("", s)
    for sep in ("/", "\\", ":"):
        s = s.replace(sep, "-")
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    if len(s) > _MAX_CHARACTER_STEM_LEN:
        s = s[:_MAX_CHARACTER_STEM_LEN].rstrip("-")
    return s


def character_stem_from_title(title: str) -> tuple[str, bool]:
    """Return ``(stem, used_fallback)`` for ``character`` default filenames; stem is never empty."""
    stem = _slug_title_for_character_filename(title)
    if not stem:
        return "character", True
    return stem, False


def character_default_output_path(
    title: str, cli_format: CliImageFormat, *, now: datetime | None = None
) -> str:
    """Default path for ``genimg character``: ``{safe_stem}-{YYYYMMDD_HHMMSS}.{ext}`` in CWD."""
    stem, _used_fallback = character_stem_from_title(title)
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    ext = cli_format_to_extension(cli_format).lstrip(".")
    return f"{stem}-{timestamp}.{ext}"


__all__ = [
    "EXIT_SUCCESS",
    "EXIT_API_OR_NETWORK",
    "EXIT_VALIDATION_OR_CONFIG",
    "EXIT_CANCELLED",
    "character_default_output_path",
    "character_stem_from_title",
    "default_output_path",
]
