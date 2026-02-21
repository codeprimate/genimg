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
    ValidationError,
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
from genimg.core.image_analysis import get_description, unload_describe_models
from genimg.core.providers import get_registry
from genimg.logging_config import configure_logging, get_verbosity_from_env


@click.group(
    help=f"""AI image generation with prompt optimization (OpenRouter + Ollama).

\b
Version: {__version__}
GitHub: https://github.com/codeprimate/genimg
Documentation: https://github.com/codeprimate/genimg#readme
Report issues: https://github.com/codeprimate/genimg/issues
"""
)
@click.version_option(
    version=__version__,
    package_name="genimg",
    message="%(prog)s %(version)s\nGitHub: https://github.com/codeprimate/genimg",
)
@click.pass_context
def cli(ctx: click.Context) -> None:
    ctx.color = True


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
    "--api-key",
    envvar="OPENROUTER_API_KEY",
    help="OpenRouter API key (overrides OPENROUTER_API_KEY environment variable).",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Minimize progress messages; only print result path or errors.",
)
@click.option(
    "--verbose",
    "-v",
    "verbose_count",
    count=True,
    help="Increase verbosity: -v also show prompts, -vv show API/cache detail.",
)
@click.option(
    "--provider",
    type=click.Choice(["openrouter", "ollama"], case_sensitive=False),
    default=None,
    help="Image generation provider (default from config: ollama or openrouter).",
)
@click.option(
    "--debug-api",
    is_flag=True,
    help="Log raw API request payload and response (image data truncated) for debugging.",
)
@click.option(
    "--use-reference-description",
    is_flag=True,
    help="Use reference image description during optimization (describe then optimize with description; with Ollama the image is not sent).",
)
@click.option(
    "--reference-description-model",
    type=click.Choice(["tags", "prose"], case_sensitive=False),
    default="prose",
    help="How to describe the reference image: 'tags' (JoyTag) or 'prose' (Florence-2). Default: prose.",
)
@click.option(
    "--reference-description-verbosity",
    type=click.Choice(["brief", "detailed", "more_detailed"], case_sensitive=False),
    default="detailed",
    help="Prose description verbosity (only for --reference-description-model prose). Default: detailed.",
)
def generate(
    prompt: str,
    model: str | None,
    reference: Path | None,
    no_optimize: bool,
    out: Path | None,
    optimization_model: str | None,
    save_prompt: Path | None,
    api_key: str | None,
    provider: str | None,
    quiet: bool,
    verbose_count: int,
    debug_api: bool,
    use_reference_description: bool,
    reference_description_model: str,
    reference_description_verbosity: str,
) -> None:
    """Generate an image from a text prompt (optionally with optimization and reference)."""
    # Reset cancel event for this run (in case CLI is invoked again in same process)
    reset_cancellation()

    # Apply logging verbosity: CLI flags override GENIMG_VERBOSITY
    verbose_level = min(verbose_count, 2) if verbose_count > 0 else get_verbosity_from_env()
    configure_logging(verbose_level=verbose_level, quiet=quiet)

    def do_generate() -> None:
        # 1. Load and validate config
        config = Config.from_env()

        # Override API key if provided via CLI
        if api_key is not None:
            config.set_api_key(api_key)
        if debug_api:
            config.debug_api = True

        config.validate()

        # 2. Effective provider (CLI override or config default)
        provider_eff = provider if provider is not None else config.default_image_provider
        if reference is not None and not use_reference_description:
            impl = get_registry().get(provider_eff)
            if impl is not None and not getattr(impl, "supports_reference_image", True):
                raise ValidationError(
                    f"Reference images are not supported for provider {provider_eff!r}. "
                    "Use --provider openrouter for reference image support.",
                    field="reference_image",
                )

        # 3. Validate prompt
        validate_prompt(prompt)

        # 4. Reference image
        ref_b64: str | None = None
        ref_hash: str | None = None
        if reference is not None:
            ref_b64, ref_hash = process_reference_image(reference, config=config)

        # 4b. Reference description (when --use-reference-description)
        description: str | None = None
        if use_reference_description and reference is not None:
            description = get_description(
                reference,
                ref_hash,
                method=reference_description_model,
                verbosity=reference_description_verbosity,
            )
            if provider_eff == "ollama":
                unload_describe_models()

        # 5. Optional optimization
        effective_prompt = prompt
        if not no_optimize:
            config.optimization_enabled = True
            ref_desc = description if (use_reference_description and description) else None
            if not quiet:
                with progress.optimization_progress(
                    model=optimization_model or config.default_optimization_model,
                    reference_used=reference is not None,
                ):
                    effective_prompt = optimize_prompt(
                        prompt,
                        model=optimization_model,
                        reference_hash=ref_hash,
                        reference_description=ref_desc,
                        config=config,
                        cancel_check=cancel_check,
                    )
            else:
                effective_prompt = optimize_prompt(
                    prompt,
                    model=optimization_model,
                    reference_hash=ref_hash,
                    reference_description=ref_desc,
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

        # 6. Generate image (pass reference image only if provider supports it)
        impl = get_registry().get(provider_eff)
        ref_b64_to_send = (
            ref_b64
            if (impl is not None and getattr(impl, "supports_reference_image", True))
            else None
        )
        gen_kw: dict = {
            "model": model,
            "reference_image_b64": ref_b64_to_send,
            "config": config,
            "cancel_check": cancel_check,
        }
        if provider is not None:
            gen_kw["provider"] = provider

        result: GenerationResult
        if not quiet:
            with progress.generation_progress(
                model=model or config.default_image_model,
                reference_used=reference is not None,
                optimized=not no_optimize,
            ):
                result = generate_image(effective_prompt, **gen_kw)
        else:
            result = generate_image(effective_prompt, **gen_kw)

        # 7. Output path
        out_path = out
        if out_path is None:
            out_path = Path(default_output_path(result.format))

        # 8. Save
        out_path.write_bytes(result.image_data)

        # 9. Print result
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
@click.option(
    "--api-key",
    envvar="OPENROUTER_API_KEY",
    help="OpenRouter API key (overrides OPENROUTER_API_KEY environment variable).",
)
@click.option(
    "--debug-api",
    is_flag=True,
    help="Log raw API request/response (image data truncated) when generating from the UI.",
)
def ui(
    port: int | None,
    host: str | None,
    share: bool | None,
    api_key: str | None,
    debug_api: bool,
) -> None:
    """Launch the Gradio web UI for image generation."""
    from genimg.ui.gradio_app import launch as launch_ui

    # Apply logging verbosity from env so UI logs respect GENIMG_VERBOSITY
    configure_logging(verbose_level=get_verbosity_from_env(), quiet=False)

    # Set API key in environment if provided via CLI so the UI can pick it up
    if api_key is not None:
        os.environ["OPENROUTER_API_KEY"] = api_key
    if debug_api:
        os.environ["GENIMG_DEBUG_API"] = "1"

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
