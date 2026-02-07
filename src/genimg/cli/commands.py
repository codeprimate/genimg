"""
Click command definitions for the genimg CLI.

This module contains the Click command group and all CLI commands
(generate, ui, etc.).
"""

import os
from pathlib import Path

import click

from genimg import (
    Config,
    GenerationResult,
    __version__,
    generate_image,
    optimize_prompt,
    process_reference_image,
    validate_prompt,
)
from genimg.cli import progress
from genimg.cli.handlers import (
    cancel_check,
    install_sigint_handler,
    reset_cancellation,
    restore_sigint_handler,
    run_with_error_handling,
)
from genimg.cli.utils import default_output_path


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
    "--save-prompt",
    type=click.Path(path_type=Path),
    help="Save optimized prompt to file (relative to CWD or absolute path).",
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
    save_prompt: Path | None,
    quiet: bool,
) -> None:
    """Generate an image from a text prompt (optionally with optimization and reference)."""
    # Reset cancel event for this run (in case CLI is invoked again in same process)
    reset_cancellation()

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
                        cancel_check=cancel_check,
                    )
            else:
                effective_prompt = optimize_prompt(
                    prompt,
                    model=optimization_model,
                    reference_hash=ref_hash,
                    config=config,
                    cancel_check=cancel_check,
                )

            # Save optimized prompt if requested
            if save_prompt is not None:
                try:
                    # Ensure parent directories exist
                    save_prompt.parent.mkdir(parents=True, exist_ok=True)
                    # Write optimized prompt as UTF-8 text
                    save_prompt.write_text(effective_prompt, encoding="utf-8")
                    if not quiet:
                        progress.print_info(f"Saved optimized prompt to {save_prompt}")
                except OSError as e:
                    # Report error but don't fail the entire operation
                    if quiet:
                        click.echo(
                            f"Warning: Could not save prompt to {save_prompt}: {e}", err=True
                        )
                    else:
                        progress.print_warning(f"Could not save prompt to {save_prompt}: {e}")

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
                    cancel_check=cancel_check,
                )
        else:
            result = generate_image(
                effective_prompt,
                model=model,
                reference_image_b64=ref_b64,
                config=config,
                cancel_check=cancel_check,
            )

        # 6. Output path
        out_path = out
        if out_path is None:
            out_path = Path(default_output_path(result.format))

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
    old_sigint = install_sigint_handler()
    try:
        run_with_error_handling(do_generate, quiet=quiet)
    finally:
        restore_sigint_handler(old_sigint)


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


__all__ = ["cli", "main", "generate", "ui"]
