"""Core Draw Things preset registry (used by ``genimg`` + Gradio)."""

import pytest

from genimg.core.providers.draw_things.presets import resolve_draw_things_preset


@pytest.mark.unit
def test_flux2_klein_preset_is_tuning_only() -> None:
    p = resolve_draw_things_preset("flux2-klein")
    assert p is not None
    assert p.steps == 5
    assert p.guidance_scale == pytest.approx(1.0)


@pytest.mark.unit
def test_z_image_preset_is_tuning_only() -> None:
    z = resolve_draw_things_preset("z-image")
    assert z is not None
    assert z.default_hires_fix is True
