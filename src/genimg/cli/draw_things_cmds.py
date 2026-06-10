"""Draw Things CLI subcommands (list LoRAs from local gRPC catalog)."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

import click

from genimg import Config
from genimg.core.providers.draw_things.lora_choices import (
    fetch_lora_catalog,
    lora_catalog_hint,
    lora_display_label,
)
from genimg.logging_config import configure_logging, get_verbosity_from_env


@click.group("draw-things", help="Draw Things local gRPC helpers.")
def draw_things_group() -> None:
    """Draw Things asset discovery and utilities."""


@draw_things_group.command("list-loras")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON array for scripting.")
def list_loras_cmd(as_json: bool) -> None:
    """List LoRA checkpoints reported by the running Draw Things app."""
    configure_logging(verbose_level=get_verbosity_from_env(), quiet=False)
    config = Config.from_env()
    result = fetch_lora_catalog(config)
    loras = result.loras
    if not loras and not as_json:
        hint = lora_catalog_hint(
            result,
            host=config.draw_things_host,
            port=config.draw_things_port,
        )
        if hint:
            click.echo(hint, err=True)

    if as_json:
        click.echo(json.dumps([asdict(x) for x in loras], indent=2))
        return

    lines: list[str] = []
    for lora in loras:
        label = lora_display_label(lora)
        if label:
            lines.append(label)
    if not lines:
        click.echo("(no LoRAs reported)")
        return
    for line in sorted(lines, key=str.lower):
        click.echo(line)


__all__ = ["draw_things_group", "list_loras_cmd"]
