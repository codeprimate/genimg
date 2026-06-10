"""Unit tests for Draw Things LoRA choice helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from genimg.core.providers.draw_things.lora_choices import (
    DEFAULT_LORA_WEIGHT,
    LoraCatalogResult,
    fetch_loras,
    lora_catalog_hint,
    lora_display_label,
    lora_dropdown_choices,
    merge_checkpoint_filenames,
    model_display_label,
    model_dropdown_choices,
    parse_lora_spec,
    parse_lora_stack,
)
from genimg.core.providers.draw_things.types import LoraInfo, ModelInfo


@pytest.mark.unit
def test_parse_lora_spec_file_only() -> None:
    assert parse_lora_spec("style.ckpt") == ("style.ckpt", DEFAULT_LORA_WEIGHT)


@pytest.mark.unit
def test_parse_lora_spec_with_weight() -> None:
    assert parse_lora_spec("style.ckpt:0.65") == ("style.ckpt", pytest.approx(0.65))


@pytest.mark.unit
def test_parse_lora_spec_empty_raises() -> None:
    with pytest.raises(ValueError):
        parse_lora_spec("   ")


@pytest.mark.unit
def test_parse_lora_stack_preserves_order_and_dedupes() -> None:
    stack = parse_lora_stack(
        ("a.ckpt:0.5", "b.ckpt", "", "a.ckpt:0.9", "c.ckpt:0.2")
    )
    assert stack == (
        ("a.ckpt", pytest.approx(0.5)),
        ("b.ckpt", DEFAULT_LORA_WEIGHT),
        ("c.ckpt", pytest.approx(0.2)),
    )


@pytest.mark.unit
def test_lora_display_label_with_name() -> None:
    label = lora_display_label(LoraInfo(file="x.ckpt", name="My Style"))
    assert label == "x.ckpt  —  My Style"


@pytest.mark.unit
def test_lora_display_label_file_only() -> None:
    assert lora_display_label(LoraInfo(file="x.ckpt", name="x.ckpt")) == "x.ckpt"


@pytest.mark.unit
def test_merge_checkpoint_filenames_preserves_order() -> None:
    merged = merge_checkpoint_filenames(
        ["flux_2_klein_9b_i8x.ckpt"],
        ["moodymix_zitv10dpo_f16.ckpt", "flux_2_klein_9b_i8x.ckpt"],
    )
    assert merged == [
        "flux_2_klein_9b_i8x.ckpt",
        "moodymix_zitv10dpo_f16.ckpt",
    ]


@pytest.mark.unit
def test_model_dropdown_choices_sorted() -> None:
    choices = model_dropdown_choices(
        (
            ModelInfo(file="b.ckpt", name="Beta"),
            ModelInfo(file="a.ckpt", name="Alpha"),
        )
    )
    assert choices[0][0] == "a.ckpt"
    assert choices[1][0] == "b.ckpt"


@pytest.mark.unit
def test_model_display_label_with_name() -> None:
    label = model_display_label(ModelInfo(file="klein.ckpt", name="FLUX Klein"))
    assert "klein.ckpt" in label
    assert "FLUX Klein" in label


@pytest.mark.unit
def test_lora_dropdown_choices_sorted() -> None:
    choices = lora_dropdown_choices(
        (
            LoraInfo(file="b.ckpt", name="Beta"),
            LoraInfo(file="a.ckpt", name="Alpha"),
        )
    )
    assert choices[0][0] == "a.ckpt"
    assert choices[1][0] == "b.ckpt"


@pytest.mark.unit
def test_fetch_loras_retries_until_catalog_populated(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    class _FakeClient:
        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def wait_for_ready(self, timeout_seconds: float = 10.0) -> None:
            del timeout_seconds

        def echo_catalog_loras(self, *, timeout_seconds: float = 5.0) -> tuple[tuple[LoraInfo, ...], bool]:
            del timeout_seconds
            calls["n"] += 1
            if calls["n"] < 3:
                return (), False
            return (LoraInfo(file="found.ckpt", name="Found"),), True

    monkeypatch.setattr(
        "genimg.core.providers.draw_things.lora_choices._draw_things_client_from_config",
        lambda _config: _FakeClient(),
    )
    monkeypatch.setattr("genimg.core.providers.draw_things.lora_choices.time.sleep", lambda _: None)

    loras = fetch_loras(MagicMock())
    assert calls["n"] == 3
    assert loras == (LoraInfo(file="found.ckpt", name="Found"),)


@pytest.mark.unit
def test_fetch_loras_stops_when_override_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    class _FakeClient:
        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def wait_for_ready(self, timeout_seconds: float = 10.0) -> None:
            del timeout_seconds

        def echo_catalog_loras(self, *, timeout_seconds: float = 5.0) -> tuple[tuple[LoraInfo, ...], bool]:
            del timeout_seconds
            calls["n"] += 1
            return (), True

    monkeypatch.setattr(
        "genimg.core.providers.draw_things.lora_choices._draw_things_client_from_config",
        lambda _config: _FakeClient(),
    )
    monkeypatch.setattr("genimg.core.providers.draw_things.lora_choices.time.sleep", lambda _: None)

    loras = fetch_loras(MagicMock())
    assert calls["n"] == 1
    assert loras == ()

@pytest.mark.unit
def test_lora_catalog_hint_no_override() -> None:
    hint = lora_catalog_hint(
        LoraCatalogResult(loras=(), reachable=True, catalog_published=False),
        host="127.0.0.1",
        port=7859,
    )
    assert "Model Browser" in hint

@pytest.mark.unit
def test_lora_catalog_hint_with_loras() -> None:
    hint = lora_catalog_hint(
        LoraCatalogResult(
            loras=(LoraInfo(file="a.ckpt", name="A"),),
            reachable=True,
            catalog_published=True,
        ),
        host="127.0.0.1",
        port=7859,
    )
    assert hint == ""
