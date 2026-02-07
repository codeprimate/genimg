"""
Logging configuration for genimg.

Provides structured logging with verbosity levels. Logging is configured lazily
so library users who never call set_verbosity or configure_logging get no
logs unless they configure logging themselves.

Verbosity levels:
- 0 (default): INFO — activity and performance only
- 1 (info): INFO + prompt text (original/optimized)
- 2 (verbose): DEBUG + prompt text — API calls, cache, etc.

Use set_verbosity(level) or configure_logging(verbose_level, quiet).
GENIMG_VERBOSITY env (0/1/2) is read when CLI runs or when configure_logging
is called; CLI flags override env.
"""

import logging
import os

LOG_FORMAT = "%(levelname)s [%(name)s] %(message)s"
ROOT_LOGGER_NAME = "genimg"

_log_prompts: bool = False
_configured: bool = False


def _ensure_handler() -> None:
    """Add a stderr handler to the root genimg logger if not already present."""
    global _configured
    if _configured:
        return
    root = logging.getLogger(ROOT_LOGGER_NAME)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
    _configured = True


def set_verbosity(level: int) -> None:
    """
    Set logging verbosity (0=default, 1=info, 2=verbose).

    - 0: INFO level; activity and performance only (no prompt text).
    - 1: INFO level; same + log prompt text (original/optimized).
    - 2: DEBUG level; same + API calls, cache, request/response (no secrets).

    Logging is controlled by set_verbosity or GENIMG_VERBOSITY env (0/1/2).
    """
    global _log_prompts
    _ensure_handler()
    root = logging.getLogger(ROOT_LOGGER_NAME)
    if level <= 0:
        root.setLevel(logging.INFO)
        _log_prompts = False
    elif level == 1:
        root.setLevel(logging.INFO)
        _log_prompts = True
    else:
        root.setLevel(logging.DEBUG)
        _log_prompts = True


def log_prompts() -> bool:
    """Return True if prompt text should be logged at INFO (verbosity 1 or 2)."""
    return _log_prompts


def configure_logging(verbose_level: int = 0, quiet: bool = False) -> None:
    """
    Configure logging from CLI or library.

    When quiet is True, sets level to WARNING (no activity/performance).
    Otherwise calls set_verbosity(verbose_level).
    """
    global _log_prompts
    _ensure_handler()
    root = logging.getLogger(ROOT_LOGGER_NAME)
    if quiet:
        root.setLevel(logging.WARNING)
        _log_prompts = False
        return
    set_verbosity(verbose_level)


def get_verbosity_from_env() -> int:
    """
    Read GENIMG_VERBOSITY from environment (0, 1, or 2).

    Invalid or missing values return 0.
    """
    raw = os.environ.get("GENIMG_VERBOSITY", "0").strip()
    if raw == "1":
        return 1
    if raw == "2":
        return 2
    return 0


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under genimg (e.g. genimg.core.image_gen)."""
    if name.startswith(ROOT_LOGGER_NAME + ".") or name == ROOT_LOGGER_NAME:
        return logging.getLogger(name)
    return logging.getLogger(ROOT_LOGGER_NAME + "." + name)


__all__ = [
    "configure_logging",
    "get_logger",
    "get_verbosity_from_env",
    "log_prompts",
    "set_verbosity",
]
