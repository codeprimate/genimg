"""Named Draw Things txt2img tuning bundles (``--preset`` on the CLI).

Each preset is a small immutable record plus a registry for lookup. Add new entries
to ``DRAW_THINGS_PRESETS``; CLI choices and help text are derived from the registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from genimg.contrib.draw_things_poc.generated.SamplerType import SamplerType


@dataclass(frozen=True, slots=True)
class DrawThingsPreset:
    """Canonical generation defaults for a model family or distilled recipe."""

    id: str
    """Lowercase CLI token (e.g. ``z-image``)."""

    title: str
    """Short human label for help text."""

    width_px: int
    height_px: int
    steps: int
    guidance_scale: float
    strength: float
    sampler: int
    """FlatBuffers ``SamplerType`` wire value."""

    default_hires_fix: bool = False
    """When true, ``generate --preset`` may set ``--hires-fix`` if you omit both hires flags."""

    default_upscaler: str | None = None
    """When set, ``generate --preset`` may fill ``--upscaler`` if you omit it (post-render upscaler)."""

    default_upscaler_scale_factor: int | None = None
    """When set with ``default_upscaler``, may fill ``--upscaler-scale`` if you omit it."""

    def sampler_wire_name(self) -> str:
        """Enum member name for ``sampler`` (for help strings)."""
        for name in dir(SamplerType):
            if name.startswith("_"):
                continue
            v = getattr(SamplerType, name)
            if isinstance(v, int) and int(v) == int(self.sampler):
                return name
        return str(int(self.sampler))

    def cli_help_sentence(self) -> str:
        """One line for ``--preset`` epilog-style documentation."""
        base = (
            f"{self.id}: {self.title} — {self.width_px}×{self.height_px}, {self.steps} steps, "
            f"CFG {self.guidance_scale}, denoise {self.strength}, default sampler "
            f"{self.sampler_wire_name()}."
        )
        bits: list[str] = []
        if self.default_hires_fix:
            bits.append("hi-res fix on if you omit --hires-fix/--no-hires-fix")
        if self.default_upscaler and self.default_upscaler_scale_factor is not None:
            bits.append(
                f"upscaler {self.default_upscaler!r} at {self.default_upscaler_scale_factor}× "
                "if you omit --upscaler / --upscaler-scale"
            )
        if bits:
            return f"{base} Preset defaults: {'; '.join(bits)}."
        return base


# Register presets here (single source of truth).
DRAW_THINGS_PRESETS: tuple[DrawThingsPreset, ...] = (
    DrawThingsPreset(
        id="z-image",
        title="Z-Image-Turbo",
        width_px=1280,
        height_px=1280,
        steps=8,
        guidance_scale=1.0,
        strength=1.0,
        sampler=int(SamplerType.UniPCTrailing),
        default_hires_fix=True,
    ),
    # FLUX.2 [klein] distilled checkpoints: keep CFG at 1.0; few steps; 1024² is a common native size.
    # Sampler DDIM approximates DDIM-style schedules often used with Klein in ComfyUI workflows.
    DrawThingsPreset(
        id="flux2-klein",
        title="FLUX.2 [klein] (distilled-style defaults)",
        width_px=1280,
        height_px=1280,
        steps=5,
        guidance_scale=1.0,
        strength=1.0,
        sampler=int(SamplerType.DDIM),
    ),
)


@cache
def _preset_by_id() -> dict[str, DrawThingsPreset]:
    by_id: dict[str, DrawThingsPreset] = {}
    for p in DRAW_THINGS_PRESETS:
        key = p.id.strip().lower()
        if key in by_id:
            raise ValueError(f"duplicate Draw Things preset id: {key!r}")
        by_id[key] = p
    return by_id


def draw_things_preset_ids() -> tuple[str, ...]:
    """Stable CLI tokens for ``click.Choice`` (registration order)."""
    return tuple(p.id for p in DRAW_THINGS_PRESETS)


def resolve_draw_things_preset(name: str | None) -> DrawThingsPreset | None:
    """Resolve a CLI ``--preset`` value; ``None`` / empty → no preset."""
    if name is None:
        return None
    s = name.strip()
    if not s:
        return None
    return _preset_by_id().get(s.lower())


def draw_things_preset_option_help() -> str:
    """Paragraph for ``--preset`` documenting every registered bundle."""
    lines = [
        "Known-good tuning bundles. For each of --width, --height, --steps, --cfg, "
        "--strength, --sampler, --hires-fix/--no-hires-fix, and (when defined) "
        "--upscaler / --upscaler-scale, the preset fills in a value only if you omit that "
        "option; anything you pass on the command line still wins.",
        "",
    ]
    lines.extend(p.cli_help_sentence() for p in DRAW_THINGS_PRESETS)
    return "\n".join(lines)
