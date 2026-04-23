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
    CLI_COMMAND_LIST_SAMPLERS,
    CLI_LIST_BANNER,
    CLI_LIST_EMPTY,
    CLI_LIST_FOOTER,
    CLI_LIST_RULE,
    CLI_LIST_SAMPLERS_FOOTER,
    CLI_LIST_SECTION_CONTROL_NETS,
    CLI_LIST_SECTION_LORAS,
    CLI_LIST_SECTION_MODELS,
    CLI_LIST_SECTION_SAMPLERS,
    CLI_LIST_SECTION_TEXTUAL_INVERSIONS,
    CLI_LIST_SECTION_UPSCALERS,
    DEFAULT_DRAW_THINGS_HOST,
    DEFAULT_DRAW_THINGS_PORT,
    Z_IMAGE_PRESET_CFG,
    Z_IMAGE_PRESET_HEIGHT,
    Z_IMAGE_PRESET_STEPS,
    Z_IMAGE_PRESET_STRENGTH,
    Z_IMAGE_PRESET_WIDTH,
)
from genimg.contrib.draw_things_poc.samplers import (
    Z_IMAGE_PRESET_SAMPLER,
    parse_sampler,
    sampler_enum_rows,
)
from genimg.contrib.draw_things_poc.tensor_image import dt_tensor_bytes_to_pil
from genimg.contrib.draw_things_poc.types import (
    ControlNetInfo,
    LoraInfo,
    ModelInfo,
    TextualInversionInfo,
    UpscalerInfo,
)


def _parse_lora_option(spec: str) -> tuple[str, float]:
    """``file.ckpt`` or ``file.ckpt:0.75`` (weight defaults to 0.8)."""
    s = spec.strip()
    if not s:
        raise click.BadParameter("empty --lora")
    if ":" in s:
        path, w = s.rsplit(":", 1)
        path = path.strip()
        if not path:
            raise click.BadParameter(spec)
        return path, float(w.strip())
    return s, 0.8


class _SamplerParam(click.ParamType):
    """``SamplerType`` wire name (``EulerA``) or integer (``0`` … ``18``)."""

    name = "sampler"

    def convert(
        self,
        value: object,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> int | None:
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        try:
            return parse_sampler(s)
        except ValueError as e:
            raise click.BadParameter(str(e), ctx=ctx, param=param) from e


SAMPLER_PARAM = _SamplerParam()


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


def _line_file_and_label(file: str, label: str) -> str | None:
    f = file.strip()
    if not f:
        return None
    n = label.strip()
    if n and n != f:
        return f"{f}  —  {n}"
    return f


def _format_models(models: tuple[ModelInfo, ...]) -> list[str]:
    lines: list[str] = []
    for m in models:
        s = _line_file_and_label(m.file, m.name)
        if s:
            lines.append(s)
    return sorted(lines, key=str.lower)


def _format_loras(items: tuple[LoraInfo, ...]) -> list[str]:
    lines: list[str] = []
    for x in items:
        s = _line_file_and_label(x.file, x.name)
        if s:
            lines.append(s)
    return sorted(lines, key=str.lower)


def _format_control_nets(items: tuple[ControlNetInfo, ...]) -> list[str]:
    lines: list[str] = []
    for x in items:
        s = _line_file_and_label(x.file, x.name)
        if s:
            lines.append(s)
    return sorted(lines, key=str.lower)


def _format_textual_inversions(items: tuple[TextualInversionInfo, ...]) -> list[str]:
    lines: list[str] = []
    for x in items:
        f = x.file.strip()
        kw = x.keyword.strip()
        nm = x.name.strip()
        if f and kw:
            tail = f"keyword: {kw}"
            if nm and nm not in (f, kw):
                tail = f"{nm}  |  keyword: {kw}"
            lines.append(f"{f}  —  {tail}")
        elif f:
            s = _line_file_and_label(f, nm)
            if s:
                lines.append(s)
        elif kw:
            lines.append(f"(keyword only)  {kw}")
    return sorted(lines, key=str.lower)


def _format_upscalers(items: tuple[UpscalerInfo, ...]) -> list[str]:
    lines: list[str] = []
    for u in items:
        s = _line_file_and_label(u.file, u.name)
        if s:
            lines.append(s)
        else:
            n = u.name.strip()
            if n:
                lines.append(n)
    return sorted(lines, key=str.lower)


def _emit_section(title: str, body_lines: list[str]) -> None:
    click.echo(title)
    click.echo("")
    if not body_lines:
        click.echo(f"  {CLI_LIST_EMPTY}")
    else:
        for line in body_lines:
            click.echo(f"  {line}")
    click.echo("")


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
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit one JSON object per line (for scripts). Default is human-readable text.",
)
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
    as_json: bool,
    kind: str,
) -> None:
    """List models, LoRAs, ControlNets, TIs, and upscalers from Echo (strings you pass to tools / config)."""
    kwargs = _client_common_kwargs(host, port, ca_pem, insecure, shared_secret)
    with DrawThingsClient(**kwargs) as client:  # type: ignore[arg-type]
        client.clear_catalog_cache()
        if as_json:
            if kind in ("all", "models"):
                click.echo(
                    json.dumps(
                        {"kind": "models", "items": [asdict(m) for m in client.list_models()]}
                    )
                )
            if kind in ("all", "loras"):
                click.echo(
                    json.dumps({"kind": "loras", "items": [asdict(m) for m in client.list_loras()]})
                )
            if kind in ("all", "control_nets"):
                click.echo(
                    json.dumps(
                        {
                            "kind": "control_nets",
                            "items": [asdict(m) for m in client.list_control_nets()],
                        }
                    )
                )
            if kind in ("all", "textual_inversions"):
                click.echo(
                    json.dumps(
                        {
                            "kind": "textual_inversions",
                            "items": [asdict(m) for m in client.list_textual_inversions()],
                        }
                    )
                )
            if kind in ("all", "upscalers"):
                click.echo(
                    json.dumps(
                        {"kind": "upscalers", "items": [asdict(m) for m in client.list_upscalers()]}
                    )
                )
            return

        click.echo(CLI_LIST_BANNER.format(host=host, port=port))
        click.echo(CLI_LIST_RULE)
        click.echo("")

        if kind in ("all", "models"):
            _emit_section(CLI_LIST_SECTION_MODELS, _format_models(client.list_models()))
        if kind in ("all", "loras"):
            _emit_section(CLI_LIST_SECTION_LORAS, _format_loras(client.list_loras()))
        if kind in ("all", "control_nets"):
            _emit_section(
                CLI_LIST_SECTION_CONTROL_NETS, _format_control_nets(client.list_control_nets())
            )
        if kind in ("all", "textual_inversions"):
            _emit_section(
                CLI_LIST_SECTION_TEXTUAL_INVERSIONS,
                _format_textual_inversions(client.list_textual_inversions()),
            )
        if kind in ("all", "upscalers"):
            _emit_section(CLI_LIST_SECTION_UPSCALERS, _format_upscalers(client.list_upscalers()))

        click.echo(CLI_LIST_FOOTER)


@main.command(name=CLI_COMMAND_LIST_SAMPLERS)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit one JSON object (FlatBuffers ``SamplerType`` wire table).",
)
def list_samplers(as_json: bool) -> None:
    """List ``SamplerType`` enum values for ``GenerationConfiguration.sampler`` (no gRPC call)."""
    rows = sampler_enum_rows()
    if as_json:
        click.echo(
            json.dumps(
                {
                    "kind": "samplers",
                    "items": [{"value": v, "name": n, "label": lbl} for v, n, lbl in rows],
                }
            )
        )
        return

    click.echo(CLI_LIST_SECTION_SAMPLERS)
    click.echo("")
    click.echo(CLI_LIST_RULE)
    click.echo("")
    for v, n, lbl in rows:
        click.echo(f"  {v:>2}  {n}  —  {lbl}")
    click.echo("")
    click.echo(CLI_LIST_SAMPLERS_FOOTER)


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
@click.option(
    "--strength",
    default=1.0,
    type=float,
    show_default=True,
    help="Main denoise strength (txt2img / img2img); Z-Image presets use 1.0.",
)
@click.option(
    "--preset",
    type=click.Choice(["z-image"], case_sensitive=False),
    default=None,
    help=(
        "z-image: Z-Image / moodyMix-style (distilled/turbo: ~6-8 steps) — sets "
        f"{Z_IMAGE_PRESET_WIDTH}×{Z_IMAGE_PRESET_HEIGHT}, {Z_IMAGE_PRESET_STEPS} steps, "
        f"CFG {Z_IMAGE_PRESET_CFG}, denoise {Z_IMAGE_PRESET_STRENGTH}, sampler UniPCTrailing. "
        "Overrides --width, --height, --steps, --cfg, and --strength; use --sampler to override sampler."
    ),
)
@click.option("--seed", default=-1, type=int, help="Use negative value for random seed.")
@click.option(
    "--sampler",
    default=None,
    type=SAMPLER_PARAM,
    help="FlatBuffers sampler (enum name or wire int); see list-samplers.",
)
@click.option(
    "--lora",
    multiple=True,
    help='LoRA checkpoint file name (from list-assets), optional weight: "file.ckpt:0.75". Repeatable.',
)
@click.option(
    "--upscaler",
    default=None,
    help="Upscaler checkpoint file name from list-assets (e.g. remacri_4x_f16.ckpt).",
)
@click.option(
    "--upscaler-scale",
    "upscaler_scale",
    type=int,
    default=None,
    help="Integer scale for hires upscale (2 = 200%%). Requires --upscaler; first pass is final/size.",
)
@click.option(
    "--hires-fix-strength",
    default=0.7,
    type=float,
    show_default=True,
    help="Denoise strength for the hires upscale stage.",
)
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
    strength: float,
    preset: str | None,
    seed: int,
    sampler: int | None,
    lora: tuple[str, ...],
    upscaler: str | None,
    upscaler_scale: int | None,
    hires_fix_strength: float,
    out: Path,
) -> None:
    """Run txt2img and save decoded PNG."""
    sampler_effective: int | None = sampler
    if preset and preset.lower() == "z-image":
        width = Z_IMAGE_PRESET_WIDTH
        height = Z_IMAGE_PRESET_HEIGHT
        steps = Z_IMAGE_PRESET_STEPS
        cfg = Z_IMAGE_PRESET_CFG
        strength = Z_IMAGE_PRESET_STRENGTH
        sampler_effective = Z_IMAGE_PRESET_SAMPLER
        if sampler is not None:
            sampler_effective = sampler
    if upscaler_scale is not None and upscaler_scale > 1 and not (upscaler and upscaler.strip()):
        raise click.UsageError("--upscaler-scale > 1 requires --upscaler.")
    kwargs = _client_common_kwargs(host, port, ca_pem, insecure, shared_secret)
    seed_val: int | None = seed if seed >= 0 else None
    loras = tuple(_parse_lora_option(x) for x in lora) if lora else None
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
            loras=loras,
            upscaler=upscaler,
            upscaler_scale_factor=upscaler_scale,
            hires_fix_strength=hires_fix_strength,
            strength=strength,
            sampler=sampler_effective,
        )
    img = dt_tensor_bytes_to_pil(raw)
    img.save(out, format="PNG")
    click.echo(f"Wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
