"""Build FlatBuffers ``GenerationConfiguration`` bytes for txt2img."""

from __future__ import annotations

import secrets
from collections.abc import Sequence

import flatbuffers  # type: ignore[import-untyped]

from genimg.contrib.draw_things_poc.constants import (
    DEFAULT_STRENGTH,
    LAYOUT_BLOCK_PX,
    MIN_DIMENSION_PX,
)
from genimg.contrib.draw_things_poc.generated import GenerationConfiguration as GenCfg
from genimg.contrib.draw_things_poc.generated.LoRA import (
    LoRAAddFile,
    LoRAAddMode,
    LoRAAddWeight,
    LoRAEnd,
    LoRAStart,
)
from genimg.contrib.draw_things_poc.generated.LoRAMode import LoRAMode
from genimg.contrib.draw_things_poc.generated.SamplerType import SamplerType
from genimg.contrib.draw_things_poc.generated.SeedMode import SeedMode


def round_dimension_to_multiple_of_64(px: int) -> int:
    """Round width/height to multiples of 64 with minimum ``MIN_DIMENSION_PX``."""
    if px < MIN_DIMENSION_PX:
        px = MIN_DIMENSION_PX
    blocks = max(1, (px + LAYOUT_BLOCK_PX // 2) // LAYOUT_BLOCK_PX)
    return blocks * LAYOUT_BLOCK_PX


def pixels_to_start_blocks(px: int) -> int:
    """Convert rounded pixel size to FlatBuffers ``start_width`` / ``start_height`` (blocks of 64)."""
    rounded = round_dimension_to_multiple_of_64(px)
    return max(1, rounded // LAYOUT_BLOCK_PX)


def resolve_seed(seed: int | None) -> int:
    """Match TS behavior: random unsigned when seed is None or negative."""
    if seed is None or seed < 0:
        return secrets.randbelow(2**32)
    return seed % (2**32)


def build_txt2img_configuration_bytes(
    *,
    model: str,
    width_px: int,
    height_px: int,
    steps: int,
    guidance_scale: float,
    seed: int | None,
    request_id: int,
    sampler: int = SamplerType.DPMPP2MKarras,
    loras: Sequence[tuple[str, float]] | None = None,
    upscaler: str | None = None,
    upscaler_scale_factor: int | None = None,
    hires_fix_strength: float = 0.7,
    strength: float = DEFAULT_STRENGTH,
    for_img2img: bool = False,
) -> bytes:
    """Pack a minimal ``GenerationConfiguration`` suitable for txt2img.

    When ``upscaler`` and ``upscaler_scale_factor`` > 1 are set, enables **hires fix** so the
    first pass runs at ``final / scale`` blocks (e.g. 2× Remacri: 1024² → 512² then upscale).

    When ``for_img2img`` is true, sets ``preserve_original_after_inpaint`` to **false** so the
    server does not snap the result back to the init image (Draw Things / dt-grpc-ts default for
    that field is **true** in ``drawThingsDefault``).
    """
    rw_px = round_dimension_to_multiple_of_64(width_px)
    rh_px = round_dimension_to_multiple_of_64(height_px)
    sw = max(1, rw_px // LAYOUT_BLOCK_PX)
    sh = max(1, rh_px // LAYOUT_BLOCK_PX)
    seed_u = resolve_seed(seed)

    loras = tuple(loras) if loras is not None else ()
    scale = int(upscaler_scale_factor) if upscaler_scale_factor is not None else 1
    use_hires = bool(upscaler and upscaler.strip() and scale > 1)
    if use_hires:
        if sw % scale != 0 or sh % scale != 0:
            raise ValueError(
                f"Hires upscale {scale}× requires start_width/start_height blocks "
                f"({sw}×{sh}) divisible by {scale}; adjust width/height."
            )
        hires_sw = sw // scale
        hires_sh = sh // scale

    builder = flatbuffers.Builder(16384 if (loras or use_hires) else 4096)
    model_off = builder.CreateString(model)

    loras_vec = 0
    if loras:
        lora_offs: list[int] = []
        for path, weight in loras:
            p = path.strip()
            if not p:
                continue
            file_off = builder.CreateString(p)
            LoRAStart(builder)
            LoRAAddFile(builder, file_off)
            LoRAAddWeight(builder, float(weight))
            LoRAAddMode(builder, int(LoRAMode.All))
            lora_offs.append(LoRAEnd(builder))
        if lora_offs:
            GenCfg.StartLorasVector(builder, len(lora_offs))
            for off in reversed(lora_offs):
                builder.PrependUOffsetTRelative(off)
            loras_vec = builder.EndVector()

    upscaler_off = 0
    if upscaler and upscaler.strip():
        upscaler_off = builder.CreateString(upscaler.strip())

    GenCfg.Start(builder)
    GenCfg.AddId(builder, int(request_id))
    GenCfg.AddStartWidth(builder, sw)
    GenCfg.AddStartHeight(builder, sh)
    GenCfg.AddSeed(builder, int(seed_u))
    GenCfg.AddSteps(builder, int(steps))
    GenCfg.AddGuidanceScale(builder, float(guidance_scale))
    GenCfg.AddStrength(builder, float(strength))
    GenCfg.AddModel(builder, model_off)
    GenCfg.AddSampler(builder, int(sampler))
    if use_hires:
        GenCfg.AddHiresFix(builder, True)
        GenCfg.AddHiresFixStartWidth(builder, hires_sw)
        GenCfg.AddHiresFixStartHeight(builder, hires_sh)
        GenCfg.AddHiresFixStrength(builder, float(hires_fix_strength))
    if upscaler_off:
        GenCfg.AddUpscaler(builder, upscaler_off)
    if use_hires:
        GenCfg.AddUpscalerScaleFactor(builder, min(255, max(1, scale)))
    GenCfg.AddSeedMode(builder, int(SeedMode.ScaleAlike))
    # Match dt-grpc-ts ``drawThingsDefault`` / ``buildConfig``: zero originals break some pipelines.
    GenCfg.AddOriginalImageHeight(builder, int(rh_px))
    GenCfg.AddOriginalImageWidth(builder, int(rw_px))
    GenCfg.AddTargetImageHeight(builder, int(rh_px))
    GenCfg.AddTargetImageWidth(builder, int(rw_px))
    GenCfg.AddNegativeOriginalImageHeight(builder, int(rh_px))
    GenCfg.AddNegativeOriginalImageWidth(builder, int(rw_px))
    GenCfg.AddMaskBlur(builder, 1.5)
    if for_img2img:
        GenCfg.AddPreserveOriginalAfterInpaint(builder, False)
    if loras_vec:
        GenCfg.AddLoras(builder, loras_vec)
    root = GenCfg.End(builder)
    builder.Finish(root)
    return bytes(builder.Output())
