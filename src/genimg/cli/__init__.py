"""
Command-line interface for genimg.

This package contains CLI implementations using Click.
Uses only the public API: from genimg import ...
"""

import os
import signal
import sys
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import click

from genimg import (
    APIError,
    CancellationError,
    Config,
    ConfigurationError,
    GenerationResult,
    GenimgError,
    ImageProcessingError,
    NetworkError,
    RequestTimeoutError,
    ValidationError,
    __version__,
    generate_image,
    optimize_prompt,
    process_reference_image,
    validate_prompt,
)
from genimg.cli import progress

# Exit codes (130 = common for SIGINT)
EXIT_SUCCESS = 0
EXIT_API_OR_NETWORK = 1
EXIT_VALIDATION_OR_CONFIG = 2
EXIT_CANCELLED = 130

# Cancellation event; set on SIGINT so cancel_check can be used by library calls
_cancel_event = threading.Event()


def _cancel_check() -> bool:
    return _cancel_event.is_set()


def _handle_sigint(_signum: int, _frame: object) -> None:
    _cancel_event.set()


def _default_output_path(fmt: str) -> str:
    """Return default output path: genimg_<YYYYMMDD>_<HHMMSS>.<ext> in current directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = fmt if fmt else "png"
    return f"genimg_{timestamp}.{ext}"


def _map_exception_to_exit(exc: BaseException) -> tuple[int, str]:
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


def _run_with_error_handling(
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
        code, msg = _map_exception_to_exit(e)
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
        code, msg = _map_exception_to_exit(e)
        if quiet:
            click.echo(msg, err=True)
        else:
            progress.print_error(msg)
        sys.exit(EXIT_API_OR_NETWORK)


@click.group()
@click.version_option(version=__version__, package_name="genimg")
def cli() -> None:
    """AI image generation with prompt optimization (OpenRouter + Ollama)."""
    pass


@cli.command()
@click.option("--prompt", "-p", required=True, help="Text description of the image to generate.")
@click.option("--model", "-m", help="OpenRouter image model ID (default from config).")
@click.option(
    "--reference",
    "-r",
    type=click.Path(exists=True, path_type=Path),
    help="Path to reference image.",
)
@click.option("--no-optimize", is_flag=True, help="Skip prompt optimization.")
@click.option("--out", "-o", type=click.Path(path_type=Path), help="Output file path.")
@click.option(
    "--optimization-model",
    help="Ollama model for optimization (default from config).",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Minimize progress messages; only print result path or errors.",
)
def generate(
    prompt: str,
    model: str | None,
    reference: Path | None,
    no_optimize: bool,
    out: Path | None,
    optimization_model: str | None,
    quiet: bool,
) -> None:
    """Generate an image from a text prompt (optionally with optimization and reference)."""
    # Reset cancel event for this run (in case CLI is invoked again in same process)
    _cancel_event.clear()

    def do_generate() -> None:
        # 1. Load and validate config
        config = Config.from_env()
        config.validate()

        # 2. Validate prompt
        validate_prompt(prompt)

        # 3. Reference image
        ref_b64: str | None = None
        ref_hash: str | None = None
        if reference is not None:
            ref_b64, ref_hash = process_reference_image(reference, config=config)

        # 4. Optional optimization
        effective_prompt = prompt
        if not no_optimize:
            config.optimization_enabled = True
            if not quiet:
                with progress.optimization_progress(
                    model=optimization_model or config.default_optimization_model,
                    reference_used=reference is not None,
                ):
                    effective_prompt = optimize_prompt(
                        prompt,
                        model=optimization_model,
                        reference_hash=ref_hash,
                        config=config,
                        cancel_check=_cancel_check,
                    )
            else:
                effective_prompt = optimize_prompt(
                    prompt,
                    model=optimization_model,
                    reference_hash=ref_hash,
                    config=config,
                    cancel_check=_cancel_check,
                )

        # 5. Generate image
        result: GenerationResult
        if not quiet:
            with progress.generation_progress(
                model=model or config.default_image_model,
                reference_used=reference is not None,
                optimized=not no_optimize,
            ):
                result = generate_image(
                    effective_prompt,
                    model=model,
                    reference_image_b64=ref_b64,
                    config=config,
                    cancel_check=_cancel_check,
                )
        else:
            result = generate_image(
                effective_prompt,
                model=model,
                reference_image_b64=ref_b64,
                config=config,
                cancel_check=_cancel_check,
            )

        # 6. Output path
        out_path = out
        if out_path is None:
            out_path = Path(_default_output_path(result.format))

        # 7. Save
        out_path.write_bytes(result.image_data)

        # 8. Print result
        if quiet:
            # Quiet mode: only output path to stdout
            click.echo(str(out_path))
        else:
            # Rich formatted output
            progress.print_success_result(
                output_path=out_path,
                generation_time=result.generation_time,
                model_used=result.model_used,
                prompt_used=effective_prompt,
                had_reference=result.had_reference,
                optimized=not no_optimize,
                original_prompt=prompt if not no_optimize else None,
            )
            # Also print path to stdout for scriptability
            click.echo(str(out_path))

    # Install SIGINT handler for cancellation
    old_sigint = signal.signal(signal.SIGINT, _handle_sigint)
    try:
        _run_with_error_handling(do_generate, quiet=quiet)
    finally:
        signal.signal(signal.SIGINT, old_sigint)


@cli.command()
@click.option(
    "--port",
    "-p",
    type=int,
    default=None,
    envvar="GENIMG_UI_PORT",
    help="Port for the Gradio server (default: 7860 or GENIMG_UI_PORT).",
)
@click.option(
    "--host",
    "host",
    type=str,
    default=None,
    envvar="GENIMG_UI_HOST",
    help="Host to bind (default: 127.0.0.1 or GENIMG_UI_HOST). Use 0.0.0.0 for LAN.",
)
@click.option(
    "--share",
    is_flag=True,
    default=None,
    envvar="GENIMG_UI_SHARE",
    help="Create a public share link (e.g. gradio.live).",
)
def ui(port: int | None, host: str | None, share: bool | None) -> None:
    """Launch the Gradio web UI for image generation."""
    from genimg.ui.gradio_app import launch as launch_ui

    # Resolve env for share: env var "1" or "true" => True
    share_val = share
    if share_val is None:
        env_share = os.environ.get("GENIMG_UI_SHARE", "").lower()
        share_val = env_share in ("1", "true", "yes")
    launch_ui(server_name=host, server_port=port, share=share_val)


def main() -> None:
    """Entry point for the genimg console script."""
    cli()


__all__ = ["cli", "main"]
