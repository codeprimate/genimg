"""Build FlatBuffers ``GenerationConfiguration`` bytes for txt2img."""

from __future__ import annotations

import secrets
from collections.abc import Sequence

import flatbuffers  # type: ignore[import-untyped]

from genimg.core.providers.draw_things.constants import (
    DEFAULT_STRENGTH,
    LAYOUT_BLOCK_PX,
    MIN_DIMENSION_PX,
)
from genimg.core.providers.draw_things.generated import GenerationConfiguration as GenCfg
from genimg.core.providers.draw_things.generated.LoRA import (
    LoRAAddFile,
    LoRAAddMode,
    LoRAAddWeight,
    LoRAEnd,
    LoRAStart,
)
from genimg.core.providers.draw_things.generated.LoRAMode import LoRAMode
from genimg.core.providers.draw_things.generated.SamplerType import SamplerType
from genimg.core.providers.draw_things.generated.SeedMode import SeedMode


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


def hires_fix_start_block_count(*, final_blocks: int, final_px: int) -> int:
    """Blocks for hires first pass: ~⅔ of ``final_px``, snapped to nearest 64 px (layout grid).

    Uses the same half-up rounding as ``round_dimension_to_multiple_of_64``. The result is
    always strictly smaller than ``final_blocks`` so the upscale stage has headroom.
    """
    if final_blocks < 2:
        raise ValueError(
            "Hires fix needs a final canvas of at least 2×64 px on this axis; "
            f"got {final_blocks} block(s) ({final_px} px after rounding)."
        )
    ideal_px = float(final_px) * (2.0 / 3.0)
    half = LAYOUT_BLOCK_PX // 2
    b = max(1, int((ideal_px + float(half)) // float(LAYOUT_BLOCK_PX)))
    return min(b, final_blocks - 1)


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
    hires_fix: bool = False,
    upscaler: str | None = None,
    upscaler_scale_factor: int | None = None,
    hires_fix_strength: float = 0.7,
    strength: float = DEFAULT_STRENGTH,
) -> bytes:
    """Pack a minimal ``GenerationConfiguration`` suitable for txt2img or img2img.

    **Hi-res fix** (``hires_fix``): two diffusion passes — first near **⅔** of the final canvas
    (each axis snapped to the nearest 64 px), then to the target size. Independent of upscaler.

    **Upscaler** (``upscaler`` + optional ``upscaler_scale_factor`` > 1): post-render upscale
    checkpoint (e.g. Remacri) after generation. Either, neither, or both may be enabled.

    ``preserve_original_after_inpaint`` is left at its FlatBuffers default (``True``) to match
    native Draw Things UI behaviour for both txt2img and img2img passes.
    """
    rw_px = round_dimension_to_multiple_of_64(width_px)
    rh_px = round_dimension_to_multiple_of_64(height_px)
    sw = max(1, rw_px // LAYOUT_BLOCK_PX)
    sh = max(1, rh_px // LAYOUT_BLOCK_PX)
    seed_u = resolve_seed(seed)

    loras = tuple(loras) if loras is not None else ()
    use_hires_fix = bool(hires_fix)
    if use_hires_fix:
        hires_sw = hires_fix_start_block_count(final_blocks=sw, final_px=rw_px)
        hires_sh = hires_fix_start_block_count(final_blocks=sh, final_px=rh_px)

    upscaler_scale = int(upscaler_scale_factor) if upscaler_scale_factor is not None else 0
    use_upscaler_scale = bool(upscaler and upscaler.strip() and upscaler_scale > 1)

    builder = flatbuffers.Builder(
        16384 if (loras or use_hires_fix or (upscaler and upscaler.strip())) else 4096
    )
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
    if use_hires_fix:
        GenCfg.AddHiresFix(builder, True)
        GenCfg.AddHiresFixStartWidth(builder, hires_sw)
        GenCfg.AddHiresFixStartHeight(builder, hires_sh)
        GenCfg.AddHiresFixStrength(builder, float(hires_fix_strength))
    if upscaler_off:
        GenCfg.AddUpscaler(builder, upscaler_off)
    if use_upscaler_scale:
        GenCfg.AddUpscalerScaleFactor(builder, min(255, upscaler_scale))
    GenCfg.AddSeedMode(builder, int(SeedMode.ScaleAlike))
    # Match dt-grpc-ts ``drawThingsDefault`` / ``buildConfig``: zero originals break some pipelines.
    GenCfg.AddOriginalImageHeight(builder, int(rh_px))
    GenCfg.AddOriginalImageWidth(builder, int(rw_px))
    GenCfg.AddTargetImageHeight(builder, int(rh_px))
    GenCfg.AddTargetImageWidth(builder, int(rw_px))
    GenCfg.AddNegativeOriginalImageHeight(builder, int(rh_px))
    GenCfg.AddNegativeOriginalImageWidth(builder, int(rw_px))
    GenCfg.AddMaskBlur(builder, 1.5)
    if loras_vec:
        GenCfg.AddLoras(builder, loras_vec)
    root = GenCfg.End(builder)
    builder.Finish(root)
    return bytes(builder.Output())
