"""Unit tests for Draw Things LoRA CLI integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from PIL import Image

from genimg.cli.commands import cli
from genimg.core.image_gen import GenerationResult
from genimg.core.providers.draw_things.types import LoraInfo
from genimg.core.providers.draw_things.lora_choices import LoraCatalogResult


@pytest.mark.unit
def test_list_loras_command_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "genimg.cli.draw_things_cmds.fetch_lora_catalog",
        lambda _config: LoraCatalogResult(
            loras=(LoraInfo(file="a.ckpt", name="Alpha"),),
            reachable=True,
            catalog_published=True,
        ),
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["draw-things", "list-loras", "--json"])
    assert result.exit_code == 0
    assert '"file": "a.ckpt"' in (result.output or "")
    assert '"name": "Alpha"' in (result.output or "")


@pytest.mark.unit
def test_list_loras_command_human_readable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "genimg.cli.draw_things_cmds.fetch_lora_catalog",
        lambda _config: LoraCatalogResult(
            loras=(LoraInfo(file="a.ckpt", name="Alpha"),),
            reachable=True,
            catalog_published=True,
        ),
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["draw-things", "list-loras"])
    assert result.exit_code == 0
    assert "a.ckpt  —  Alpha" in (result.output or "")


@pytest.mark.unit
@patch("genimg.cli.commands.generate_image")
@patch("genimg.cli.commands.validate_prompt")
@patch("genimg.cli.commands.Config")
def test_generate_lora_sets_config_for_draw_things(
    mock_config_cls: MagicMock,
    _mock_validate: MagicMock,
    mock_generate: MagicMock,
) -> None:
    config = MagicMock()
    config.default_image_provider = "draw_things"
    mock_config_cls.from_env.return_value = config
    config.validate.return_value = None
    mock_generate.return_value = GenerationResult(
        image=Image.new("RGB", (1, 1)),
        _format="png",
        generation_time=1.0,
        model_used="m.ckpt",
        prompt_used="x",
        had_reference=False,
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "--prompt",
            "test",
            "--provider",
            "draw_things",
            "--no-optimize",
            "--quiet",
            "--lora",
            "style.ckpt:0.6",
            "--lora",
            "detail.ckpt",
        ],
    )
    assert result.exit_code == 0
    assert config.draw_things_loras == (
        ("style.ckpt", 0.6),
        ("detail.ckpt", 0.8),
    )


@pytest.mark.unit
@patch("genimg.cli.commands.Config")
def test_generate_lora_rejected_for_openrouter(mock_config_cls: MagicMock) -> None:
    config = MagicMock()
    config.default_image_provider = "openrouter"
    mock_config_cls.from_env.return_value = config
    config.validate.return_value = None

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate",
            "--prompt",
            "test",
            "--provider",
            "openrouter",
            "--no-optimize",
            "--lora",
            "x.ckpt",
        ],
    )
    assert result.exit_code != 0
    assert "draw_things" in (result.output or "").lower()


@pytest.mark.unit
@patch("genimg.cli.commands.generate_image")
@patch("genimg.cli.commands.process_reference_image")
@patch("genimg.cli.commands.validate_prompt")
@patch("genimg.cli.commands.Config")
def test_character_lora_sets_config_for_draw_things(
    mock_config_cls: MagicMock,
    _mock_validate: MagicMock,
    mock_process_ref: MagicMock,
    mock_generate: MagicMock,
    tmp_path: Path,
) -> None:
    config = MagicMock()
    mock_config_cls.from_env.return_value = config
    config.validate.return_value = None
    mock_process_ref.return_value = ("b64", "hash")
    mock_generate.return_value = GenerationResult(
        image=Image.new("RGB", (1, 1)),
        _format="png",
        generation_time=1.0,
        model_used="flux.ckpt",
        prompt_used="x",
        had_reference=True,
    )
    ref = tmp_path / "ref.png"
    ref.write_bytes(b"\x89PNG\r\n\x1a\n")
    out = tmp_path / "out.webp"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "character",
            "Hero",
            str(ref),
            "--provider",
            "draw_things",
            "--quiet",
            "--out",
            str(out),
            "--lora",
            "custom.ckpt:0.95",
        ],
    )
    assert result.exit_code == 0
    assert config.draw_things_loras == (("custom.ckpt", 0.95),)
