"""Core Draw Things preset registry (used by ``genimg`` + Gradio)."""

import pytest

from genimg.core.providers.draw_things.presets import (
    CHARACTER_COMMAND_DRAW_THINGS_PRESET_ID,
    resolve_draw_things_preset,
)


@pytest.mark.unit
def test_flux2_klein_preset_includes_default_loras() -> None:
    p = resolve_draw_things_preset(CHARACTER_COMMAND_DRAW_THINGS_PRESET_ID)
    assert p is not None
    assert p.default_loras == (
        ("bfs_head_v1_flux_klein_9b_step3500_rank128_lora_f16.ckpt", 0.95),
        ("klein_snofs_v1_3_lora_f16.ckpt", 0.95),
    )


@pytest.mark.unit
def test_z_image_preset_has_no_default_loras() -> None:
    z = resolve_draw_things_preset("z-image")
    assert z is not None
    assert z.default_loras == ()
