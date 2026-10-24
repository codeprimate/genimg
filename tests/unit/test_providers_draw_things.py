"""Unit tests for core Draw Things provider behavior."""

from __future__ import annotations

import pytest
from PIL import Image

from genimg.core.config import Config
from genimg.core.providers.draw_things.generated.SamplerType import SamplerType
from genimg.core.providers.draw_things.provider import DrawThingsProvider
from genimg.utils.exceptions import ValidationError


class _CaptureClient:
    last_kwargs: dict[str, object] | None = None

    def __init__(self, **_: object) -> None:
        return None

    def __enter__(self) -> _CaptureClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def generate_image_last_tensor(self, **kwargs: object) -> bytes:
        _CaptureClient.last_kwargs = kwargs
        return b"raw-tensor"


@pytest.mark.unit
def test_provider_uses_preset_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "genimg.core.providers.draw_things.provider.DrawThingsClient",
        _CaptureClient,
    )
    monkeypatch.setattr(
        "genimg.core.providers.draw_things.provider.dt_tensor_bytes_to_pil",
        lambda _: Image.new("RGB", (1, 1)),
    )

    cfg = Config()
    cfg.draw_things_preset = "z-image"  # type: ignore[attr-defined]

    provider = DrawThingsProvider()
    result = provider.generate("prompt", "m.ckpt", None, 15, cfg, None)

    assert result.image.size == (1, 1)
    assert _CaptureClient.last_kwargs is not None
    assert _CaptureClient.last_kwargs["width_px"] == 1280
    assert _CaptureClient.last_kwargs["height_px"] == 1280
    assert _CaptureClient.last_kwargs["steps"] == 8
    assert _CaptureClient.last_kwargs["guidance_scale"] == pytest.approx(1.0)
    assert _CaptureClient.last_kwargs["strength"] == pytest.approx(0.8)
    assert _CaptureClient.last_kwargs["sampler"] == int(SamplerType.UniPCTrailing)
    assert _CaptureClient.last_kwargs["hires_fix"] is True
    assert _CaptureClient.last_kwargs["upscaler"] == "remacri_4x_f16.ckpt"
    assert _CaptureClient.last_kwargs["upscaler_scale_factor"] == 2


@pytest.mark.unit
def test_provider_override_wins_over_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "genimg.core.providers.draw_things.provider.DrawThingsClient",
        _CaptureClient,
    )
    monkeypatch.setattr(
        "genimg.core.providers.draw_things.provider.dt_tensor_bytes_to_pil",
        lambda _: Image.new("RGB", (1, 1)),
    )

    cfg = Config()
    cfg.draw_things_preset = "z-image"  # type: ignore[attr-defined]
    cfg.draw_things_steps = 17  # type: ignore[attr-defined]

    provider = DrawThingsProvider()
    provider.generate("prompt", "m.ckpt", None, 15, cfg, None)

    assert _CaptureClient.last_kwargs is not None
    assert _CaptureClient.last_kwargs["steps"] == 17
    assert _CaptureClient.last_kwargs["width_px"] == 1280


@pytest.mark.unit
def test_provider_invalid_preset_raises_validation_error() -> None:
    cfg = Config()
    cfg.draw_things_preset = "nope"  # type: ignore[attr-defined]

    provider = DrawThingsProvider(grpc_stub=object())  # type: ignore[arg-type]
    with pytest.raises(ValidationError) as exc:
        provider.generate("prompt", "m.ckpt", None, 15, cfg, None)

    assert exc.value.field == "draw_things_preset"


@pytest.mark.unit
def test_provider_config_loras_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "genimg.core.providers.draw_things.provider.DrawThingsClient",
        _CaptureClient,
    )
    monkeypatch.setattr(
        "genimg.core.providers.draw_things.provider.dt_tensor_bytes_to_pil",
        lambda _: Image.new("RGB", (1, 1)),
    )

    cfg = Config()
    cfg.draw_things_preset = "flux2-klein"  # type: ignore[attr-defined]
    cfg.draw_things_loras = (("override.ckpt", 0.5),)  # type: ignore[attr-defined]

    provider = DrawThingsProvider()
    provider.generate("prompt", "m.ckpt", None, 15, cfg, None)

    assert _CaptureClient.last_kwargs is not None
    assert _CaptureClient.last_kwargs["loras"] == (("override.ckpt", 0.5),)


@pytest.mark.unit
def test_provider_does_not_apply_preset_loras(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "genimg.core.providers.draw_things.provider.DrawThingsClient",
        _CaptureClient,
    )
    monkeypatch.setattr(
        "genimg.core.providers.draw_things.provider.dt_tensor_bytes_to_pil",
        lambda _: Image.new("RGB", (1, 1)),
    )

    cfg = Config()
    cfg.draw_things_preset = "flux2-klein"  # type: ignore[attr-defined]

    provider = DrawThingsProvider()
    provider.generate("prompt", "m.ckpt", None, 15, cfg, None)

    assert _CaptureClient.last_kwargs is not None
    assert _CaptureClient.last_kwargs["loras"] is None


def _install_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "genimg.core.providers.draw_things.provider.DrawThingsClient",
        _CaptureClient,
    )
    monkeypatch.setattr(
        "genimg.core.providers.draw_things.provider.dt_tensor_bytes_to_pil",
        lambda _: Image.new("RGB", (1, 1)),
    )


@pytest.mark.unit
def test_omitted_pair_keeps_env_width(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_capture(monkeypatch)
    cfg = Config()
    cfg.draw_things_preset = "z-image"  # type: ignore[attr-defined]
    cfg.draw_things_width_px = 768  # type: ignore[attr-defined]

    DrawThingsProvider().generate("prompt", "m.ckpt", None, 15, cfg, None)

    assert _CaptureClient.last_kwargs is not None
    assert _CaptureClient.last_kwargs["width_px"] == 768
    assert _CaptureClient.last_kwargs["height_px"] == 1280


@pytest.mark.unit
def test_size_pair_replaces_preset_canvas(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_capture(monkeypatch)
    cfg = Config()
    cfg.draw_things_preset = "z-image"  # type: ignore[attr-defined]
    cfg.draw_things_width_px = 768  # type: ignore[attr-defined]
    cfg.draw_things_height_px = 768  # type: ignore[attr-defined]
    cfg.draw_things_loras = (("keep.ckpt", 0.4),)  # type: ignore[attr-defined]

    DrawThingsProvider().generate(
        "prompt",
        "m.ckpt",
        None,
        15,
        cfg,
        None,
        aspect_ratio="16:9",
        max_extent=2048,
    )

    assert _CaptureClient.last_kwargs is not None
    assert _CaptureClient.last_kwargs["width_px"] == 2048
    assert _CaptureClient.last_kwargs["height_px"] == 1152
    assert _CaptureClient.last_kwargs["steps"] == 8
    assert _CaptureClient.last_kwargs["loras"] == (("keep.ckpt", 0.4),)


@pytest.mark.unit
def test_auto_pair_requests_a_square_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_capture(monkeypatch)
    cfg = Config()
    DrawThingsProvider().generate(
        "prompt",
        "m.ckpt",
        None,
        15,
        cfg,
        None,
        aspect_ratio="auto",
        max_extent=1024,
    )
    assert _CaptureClient.last_kwargs is not None
    assert _CaptureClient.last_kwargs["width_px"] == 1024
    assert _CaptureClient.last_kwargs["height_px"] == 1024


@pytest.mark.unit
def test_size_pair_rounds_to_the_64_pixel_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    from genimg.core.output_size import ideal_pixel_size
    from genimg.core.providers.draw_things.config_builder import round_dimension_to_multiple_of_64

    _install_capture(monkeypatch)
    ideal_width, ideal_height = ideal_pixel_size("7:5", 1024)
    assert ideal_height % 64 != 0

    DrawThingsProvider().generate(
        "prompt",
        "m.ckpt",
        None,
        15,
        Config(),
        None,
        aspect_ratio="7:5",
        max_extent=1024,
    )

    assert _CaptureClient.last_kwargs is not None
    assert _CaptureClient.last_kwargs["width_px"] == round_dimension_to_multiple_of_64(ideal_width)
    assert _CaptureClient.last_kwargs["height_px"] == round_dimension_to_multiple_of_64(
        ideal_height
    )
    assert _CaptureClient.last_kwargs["height_px"] != ideal_height
