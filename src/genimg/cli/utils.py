"""
Utility functions for the CLI.

This module contains helper functions used by CLI commands,
such as path generation and exit code constants.
"""

from datetime import datetime

# Exit codes (130 = common for SIGINT)
EXIT_SUCCESS = 0
EXIT_API_OR_NETWORK = 1
EXIT_VALIDATION_OR_CONFIG = 2
EXIT_CANCELLED = 130


def default_output_path(fmt: str) -> str:
    """Return default output path: genimg_<YYYYMMDD>_<HHMMSS>.<ext> in current directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = fmt if fmt else "png"
    return f"genimg_{timestamp}.{ext}"


__all__ = [
    "EXIT_SUCCESS",
    "EXIT_API_OR_NETWORK",
    "EXIT_VALIDATION_OR_CONFIG",
    "EXIT_CANCELLED",
    "default_output_path",
]
