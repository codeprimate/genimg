"""
Error handling and signal management for the CLI.

This module provides utilities for handling exceptions, mapping them to
appropriate exit codes, and managing cancellation via SIGINT signals.
"""

import signal
import sys
import threading
from collections.abc import Callable

import click

from genimg import (
    APIError,
    CancellationError,
    ConfigurationError,
    GenimgError,
    ImageProcessingError,
    NetworkError,
    RequestTimeoutError,
    ValidationError,
)
from genimg.cli import progress
from genimg.cli.utils import (
    EXIT_API_OR_NETWORK,
    EXIT_CANCELLED,
    EXIT_VALIDATION_OR_CONFIG,
)

# Cancellation event; set on SIGINT so cancel_check can be used by library calls
_cancel_event = threading.Event()


def cancel_check() -> bool:
    """Return True if cancellation has been requested."""
    return _cancel_event.is_set()


def handle_sigint(_signum: int, _frame: object) -> None:
    """Signal handler for SIGINT (Ctrl+C) - sets cancellation event."""
    _cancel_event.set()


def reset_cancellation() -> None:
    """Reset the cancellation event for a new operation."""
    _cancel_event.clear()


def map_exception_to_exit(exc: BaseException) -> tuple[int, str]:
    """Map library and known exceptions to (exit_code, user_message)."""
    if isinstance(exc, ValidationError):
        msg = exc.args[0] if exc.args else "Validation failed."
        if getattr(exc, "field", None):
            msg = f"{msg} (field: {exc.field})"
        return (EXIT_VALIDATION_OR_CONFIG, msg)
    if isinstance(exc, ConfigurationError):
        return (EXIT_VALIDATION_OR_CONFIG, exc.args[0] if exc.args else "Invalid configuration.")
    if isinstance(exc, ImageProcessingError):
        return (EXIT_VALIDATION_OR_CONFIG, exc.args[0] if exc.args else "Image processing failed.")
    if isinstance(exc, CancellationError):
        return (EXIT_CANCELLED, "Cancelled.")
    if isinstance(exc, (APIError, NetworkError, RequestTimeoutError)):
        return (EXIT_API_OR_NETWORK, exc.args[0] if exc.args else "API or network error.")
    if isinstance(exc, GenimgError):
        return (EXIT_API_OR_NETWORK, exc.args[0] if exc.args else "An error occurred.")
    # Unhandled
    return (EXIT_API_OR_NETWORK, str(exc) if exc.args else "An unexpected error occurred.")


def run_with_error_handling(
    fn: Callable[[], None],
    *,
    quiet: bool = False,
    debug: bool = False,
) -> None:
    """
    Run fn(); on exception map to exit code and message, print and sys.exit.
    Used so the generate flow stays free of try/except for known errors.
    """
    try:
        fn()
    except (
        ValidationError,
        ConfigurationError,
        ImageProcessingError,
        CancellationError,
        APIError,
        NetworkError,
        RequestTimeoutError,
        GenimgError,
    ) as e:
        code, msg = map_exception_to_exit(e)
        if code == EXIT_CANCELLED:
            if not quiet:
                progress.print_warning(msg)
        else:
            if quiet:
                click.echo(msg, err=True)
            else:
                progress.print_error(msg)
        sys.exit(code)
    except Exception as e:
        if debug:
            raise
        code, msg = map_exception_to_exit(e)
        if quiet:
            click.echo(msg, err=True)
        else:
            progress.print_error(msg)
        sys.exit(EXIT_API_OR_NETWORK)


def install_sigint_handler() -> signal.Handlers:
    """Install SIGINT handler for cancellation, return old handler."""
    old_handler = signal.signal(signal.SIGINT, handle_sigint)
    return old_handler  # type: ignore[return-value]


def restore_sigint_handler(old_handler: signal.Handlers) -> None:
    """Restore previous SIGINT handler."""
    signal.signal(signal.SIGINT, old_handler)


__all__ = [
    "cancel_check",
    "handle_sigint",
    "reset_cancellation",
    "map_exception_to_exit",
    "run_with_error_handling",
    "install_sigint_handler",
    "restore_sigint_handler",
]
