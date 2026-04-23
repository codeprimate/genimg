"""Build FlatBuffers ``GenerationConfiguration`` bytes for txt2img."""

from __future__ import annotations

import secrets

import flatbuffers  # type: ignore[import-untyped]

from genimg.contrib.draw_things_poc.constants import (
    DEFAULT_STRENGTH,
    LAYOUT_BLOCK_PX,
    MIN_DIMENSION_PX,
)
from genimg.contrib.draw_things_poc.generated import GenerationConfiguration as GenCfg
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
) -> bytes:
    """Pack a minimal ``GenerationConfiguration`` suitable for txt2img."""
    sw = pixels_to_start_blocks(width_px)
    sh = pixels_to_start_blocks(height_px)
    seed_u = resolve_seed(seed)

    builder = flatbuffers.Builder(4096)
    model_off = builder.CreateString(model)

    GenCfg.Start(builder)
    GenCfg.AddId(builder, int(request_id))
    GenCfg.AddStartWidth(builder, sw)
    GenCfg.AddStartHeight(builder, sh)
    GenCfg.AddSeed(builder, int(seed_u))
    GenCfg.AddSteps(builder, int(steps))
    GenCfg.AddGuidanceScale(builder, float(guidance_scale))
    GenCfg.AddStrength(builder, float(DEFAULT_STRENGTH))
    GenCfg.AddModel(builder, model_off)
    GenCfg.AddSampler(builder, int(sampler))
    GenCfg.AddSeedMode(builder, int(SeedMode.ScaleAlike))
    # Schema defaults cover batching, hires, etc.
    root = GenCfg.End(builder)
    builder.Finish(root)
    return bytes(builder.Output())
