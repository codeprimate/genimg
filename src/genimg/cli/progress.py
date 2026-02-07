"""
Rich progress displays for CLI operations.

This module provides visually appealing progress indicators for CLI operations
using the rich library. All output goes to stderr to preserve stdout for
machine-readable output.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

# Console for stderr output (preserves stdout for machine output)
console = Console(stderr=True)


@contextmanager
def optimization_progress(
    model: str | None = None,
    reference_used: bool = False,
) -> Iterator[None]:
    """
    Display a spinner during prompt optimization.

    Args:
        model: The optimization model being used
        reference_used: Whether a reference image is being used

    Yields:
        None while optimization is in progress
    """
    progress = Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn("[cyan]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,  # Disappears when done
    )

    # Build description
    desc_parts = ["Optimizing prompt"]
    if model:
        desc_parts.append(f"[dim]({model})[/dim]")
    if reference_used:
        desc_parts.append("[dim cyan]with reference[/dim cyan]")

    with progress:
        task = progress.add_task(" ".join(desc_parts), total=None)
        yield
        progress.update(task, completed=True)


@contextmanager
def generation_progress(
    model: str | None = None,
    reference_used: bool = False,
    optimized: bool = False,
) -> Iterator[None]:
    """
    Display a progress bar during image generation.

    Args:
        model: The image generation model being used
        reference_used: Whether a reference image is being used
        optimized: Whether the prompt was optimized

    Yields:
        None while generation is in progress
    """
    progress = Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn("[green]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )

    # Build description
    desc_parts = ["Generating image"]
    if model:
        # Truncate long model names
        model_display = model if len(model) <= 40 else f"{model[:37]}..."
        desc_parts.append(f"[dim]({model_display})[/dim]")

    # Add feature indicators
    features = []
    if optimized:
        features.append("[dim green]optimized[/dim green]")
    if reference_used:
        features.append("[dim cyan]with reference[/dim cyan]")

    if features:
        desc_parts.append("• " + " + ".join(features))

    with progress:
        task = progress.add_task(" ".join(desc_parts), total=None)
        yield
        progress.update(task, completed=True)


def print_success_result(
    output_path: Path,
    generation_time: float,
    model_used: str,
    prompt_used: str,
    had_reference: bool,
    optimized: bool,
    original_prompt: str | None = None,
) -> None:
    """
    Print a rich formatted success message with generation details.

    Args:
        output_path: Path where the image was saved
        generation_time: Time taken to generate (seconds)
        model_used: The model that generated the image
        prompt_used: The final prompt that was used (optimized or original)
        had_reference: Whether a reference image was used
        optimized: Whether the prompt was optimized
        original_prompt: The original input prompt (if different from prompt_used)
    """
    # Create a table for the details
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan", justify="right", vertical="top")
    table.add_column(style="white")

    # Add rows
    table.add_row("Saved to", f"[bold green]{output_path}[/bold green]")
    table.add_row("Model", model_used)
    table.add_row("Time", f"{generation_time:.1f}s")

    # Add feature flags
    features = []
    if optimized:
        features.append("[green]✓[/green] Optimized")
    if had_reference:
        features.append("[cyan]✓[/cyan] Reference image")

    if features:
        table.add_row("Features", " • ".join(features))

    # Show original prompt if optimization was used and it's different
    if optimized and original_prompt and original_prompt != prompt_used:
        table.add_row("Input", f"[dim]{original_prompt}[/dim]")
        table.add_row("Optimized", f"[dim]{prompt_used}[/dim]")
    else:
        # Show the prompt used (no truncation)
        table.add_row("Prompt", f"[dim]{prompt_used}[/dim]")

    # Create a panel
    panel = Panel(
        table,
        title="[bold green]✓ Image Generated[/bold green]",
        border_style="green",
        padding=(1, 2),
    )

    console.print()
    console.print(panel)


def print_info(message: str) -> None:
    """Print an info message in cyan."""
    console.print(f"[cyan]ℹ[/cyan] {message}")


def print_warning(message: str) -> None:
    """Print a warning message in yellow."""
    console.print(f"[yellow]⚠[/yellow] {message}")


def print_error(message: str) -> None:
    """Print an error message in red."""
    console.print(f"[red]✗[/red] {message}")


def print_success(message: str) -> None:
    """Print a success message in green."""
    console.print(f"[green]✓[/green] {message}")
