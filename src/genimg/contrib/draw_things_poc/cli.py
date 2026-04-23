"""CLI for Draw Things gRPC PoC (list assets, generate)."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import click

from genimg.contrib.draw_things_poc.client import DrawThingsClient
from genimg.contrib.draw_things_poc.constants import (
    CLI_COMMAND_GENERATE,
    CLI_COMMAND_LIST_ASSETS,
    DEFAULT_DRAW_THINGS_HOST,
    DEFAULT_DRAW_THINGS_PORT,
)
from genimg.contrib.draw_things_poc.tensor_image import dt_tensor_bytes_to_pil


def _client_common_kwargs(
    host: str,
    port: int,
    ca_pem: Path | None,
    insecure: bool,
    shared_secret: str | None,
) -> dict[str, object]:
    return {
        "host": host,
        "port": port,
        "root_ca_pem_path": ca_pem,
        "use_tls": not insecure,
        "insecure": insecure,
        "shared_secret": shared_secret,
    }


@click.group()
def main() -> None:
    """Draw Things gRPC PoC commands."""


@main.command(name=CLI_COMMAND_LIST_ASSETS)
@click.option("--host", default=DEFAULT_DRAW_THINGS_HOST, show_default=True)
@click.option("--port", default=DEFAULT_DRAW_THINGS_PORT, type=int, show_default=True)
@click.option("--ca-pem", type=click.Path(path_type=Path), default=None)
@click.option("--insecure", is_flag=True, default=False)
@click.option("--shared-secret", default=None)
@click.option(
    "--kind",
    type=click.Choice(
        ["all", "models", "loras", "control_nets", "textual_inversions", "upscalers"],
        case_sensitive=False,
    ),
    default="all",
)
def list_assets(
    host: str,
    port: int,
    ca_pem: Path | None,
    insecure: bool,
    shared_secret: str | None,
    kind: str,
) -> None:
    """Print zoo catalog from Echo (JSON lines)."""
    kwargs = _client_common_kwargs(host, port, ca_pem, insecure, shared_secret)
    with DrawThingsClient(**kwargs) as client:  # type: ignore[arg-type]
        client.clear_catalog_cache()
        if kind in ("all", "models"):
            click.echo(json.dumps({"kind": "models", "items": [asdict(m) for m in client.list_models()]}))
        if kind in ("all", "loras"):
            click.echo(json.dumps({"kind": "loras", "items": [asdict(m) for m in client.list_loras()]}))
        if kind in ("all", "control_nets"):
            click.echo(
                json.dumps({"kind": "control_nets", "items": [asdict(m) for m in client.list_control_nets()]})
            )
        if kind in ("all", "textual_inversions"):
            click.echo(
                json.dumps(
                    {"kind": "textual_inversions", "items": [asdict(m) for m in client.list_textual_inversions()]}
                )
            )
        if kind in ("all", "upscalers"):
            click.echo(json.dumps({"kind": "upscalers", "items": [asdict(m) for m in client.list_upscalers()]}))


@main.command(name=CLI_COMMAND_GENERATE)
@click.option("--host", default=DEFAULT_DRAW_THINGS_HOST, show_default=True)
@click.option("--port", default=DEFAULT_DRAW_THINGS_PORT, type=int, show_default=True)
@click.option("--ca-pem", type=click.Path(path_type=Path), default=None)
@click.option("--insecure", is_flag=True, default=False)
@click.option("--shared-secret", default=None)
@click.option("--prompt", required=True)
@click.option("--model", required=True)
@click.option("--width", default=512, type=int, show_default=True)
@click.option("--height", default=512, type=int, show_default=True)
@click.option("--steps", default=20, type=int, show_default=True)
@click.option("--cfg", default=7.0, type=float, show_default=True)
@click.option("--seed", default=-1, type=int, help="Use negative value for random seed.")
@click.option("--out", type=click.Path(path_type=Path), required=True)
def generate_cmd(
    host: str,
    port: int,
    ca_pem: Path | None,
    insecure: bool,
    shared_secret: str | None,
    prompt: str,
    model: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
    out: Path,
) -> None:
    """Run txt2img and save decoded PNG."""
    kwargs = _client_common_kwargs(host, port, ca_pem, insecure, shared_secret)
    seed_val: int | None = seed if seed >= 0 else None
    with DrawThingsClient(**kwargs) as client:  # type: ignore[arg-type]
        raw = client.generate_image_last_tensor(
            prompt=prompt,
            model=model,
            width_px=width,
            height_px=height,
            steps=steps,
            guidance_scale=cfg,
            seed=seed_val,
            timeout_seconds=600.0,
        )
    img = dt_tensor_bytes_to_pil(raw)
    img.save(out, format="PNG")
    click.echo(f"Wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
