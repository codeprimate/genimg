"""
Command-line interface for genimg.

This package contains CLI implementations using Click.
"""

from typing import Optional

import click

from genimg import __version__


@click.group()
@click.version_option(version=__version__, package_name="genimg")
def cli() -> None:
    """AI image generation with prompt optimization (OpenRouter + Ollama)."""
    pass


@cli.command()
@click.option("--prompt", "-p", required=True, help="Text description of the image to generate.")
@click.option("--model", "-m", help="OpenRouter model ID (default from config).")
@click.option("--reference", "-r", type=click.Path(exists=True), help="Path to reference image.")
@click.option("--no-optimize", is_flag=True, help="Skip prompt optimization.")
@click.option("--out", "-o", type=click.Path(), help="Output file path.")
def generate(
    prompt: str,
    model: Optional[str],
    reference: Optional[str],
    no_optimize: bool,
    out: Optional[str],
) -> None:
    """Generate an image from a text prompt (optionally with optimization and reference)."""
    click.echo("CLI generate: implementation in progress. Use the library API in the meantime.")
    click.echo(
        f"  prompt={prompt!r}, model={model!r}, reference={reference!r}, "
        f"no_optimize={no_optimize}, out={out!r}"
    )


def main() -> None:
    """Entry point for the genimg console script."""
    cli()


__all__ = ["cli", "main"]
