"""Unit tests for the genimg CLI."""

import base64
import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner, Result
from PIL import Image

from genimg import DEFAULT_IMAGE_MODEL
from genimg.cli import cli
from genimg.cli.character_prompt import CHARACTER_TURNAROUND_PROMPT
from genimg.core.image_gen import GENIMG_PNG_JSON_KEYWORD, GenerationResult
from genimg.core.reference import merge_jpeg_base64_references_horizontally
from genimg.utils.exceptions import (
    APIError,
    CancellationError,
    ConfigurationError,
    ValidationError,
)


def _run_cli(*args: str) -> Result:
    """Invoke genimg generate with given args; returns Click's Result."""
    runner = CliRunner()
    return runner.invoke(cli, ["generate", "--format", "png", *args])


def _run_character(*args: str) -> Result:
    """Invoke genimg character with given args (Click merges streams into ``output``)."""
    runner = CliRunner()
    return runner.invoke(cli, ["character", "--format", "png", *args])


@pytest.mark.unit
def test_generate_help_lists_draw_things_provider() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["generate", "--help"])
    assert result.exit_code == 0
    assert "draw_things" in (result.output or "")


@pytest.mark.unit
def test_character_help_lists_draw_things_provider() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["character", "--help"])
    assert result.exit_code == 0
    assert "draw_things" in (result.output or "")


_CLI_MINIMAL_PNG_BUF = io.BytesIO()
Image.new("RGB", (1, 1), color=(0, 0, 0)).save(_CLI_MINIMAL_PNG_BUF, format="PNG")
_CLI_MINIMAL_PNG = _CLI_MINIMAL_PNG_BUF.getvalue()

_CLI_MINIMAL_JPEG_BUF = io.BytesIO()
Image.new("RGB", (1, 1), color=(0, 0, 0)).save(_CLI_MINIMAL_JPEG_BUF, format="JPEG", quality=90)
_CLI_MINIMAL_JPEG = _CLI_MINIMAL_JPEG_BUF.getvalue()


def _png_generation_result(**kwargs: object) -> GenerationResult:
    pil = Image.open(io.BytesIO(_CLI_MINIMAL_PNG)).copy()
    defaults: dict = {
        "image": pil,
        "_format": "png",
        "generation_time": 1.0,
        "model_used": "test/model",
        "prompt_used": "a cat",
        "had_reference": False,
    }
    defaults.update(kwargs)
    return GenerationResult(**defaults)


def _jpeg_generation_result(**kwargs: object) -> GenerationResult:
    pil = Image.open(io.BytesIO(_CLI_MINIMAL_JPEG)).copy()
    defaults: dict = {
        "image": pil,
        "_format": "jpeg",
        "generation_time": 0.5,
        "model_used": "test/model",
        "prompt_used": "x",
        "had_reference": False,
    }
    defaults.update(kwargs)
    return GenerationResult(**defaults)


def _assert_saved_png_cli_metadata(
    path: Path,
    *,
    description: str,
    provider: str,
    optimized: bool,
    cli: str,
    had_reference: bool | None = None,
    original_prompt: str | None = None,
    user_prompt: str | None = None,
) -> None:
    im = Image.open(path)
    im.load()
    text = dict(im.text)
    assert text["Description"] == description
    assert text["Software"].startswith("genimg ")
    meta = json.loads(text[GENIMG_PNG_JSON_KEYWORD])
    assert meta["provider"] == provider
    assert meta["optimized"] is optimized
    assert meta["cli"] == cli
    if had_reference is not None:
        assert meta["had_reference"] is had_reference
    if original_prompt is not None:
        assert meta.get("original_prompt") == original_prompt
    else:
        assert "original_prompt" not in meta
    if user_prompt is not None:
        assert meta.get("user_prompt") == user_prompt
    else:
        assert "user_prompt" not in meta


@pytest.mark.unit
class TestGenerateCommand:
    """Test generate command behavior and exit codes."""

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_required_prompt(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        _mock_optimize: MagicMock,
        _mock_generate: MagicMock,
    ) -> None:
        """Invoking without --prompt fails (Click required option)."""
        result = _run_cli()
        assert result.exit_code != 0
        assert "prompt" in result.output.lower() or "Missing" in result.output

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_no_optimize_skips_optimization(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        mock_validate: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """With --no-optimize, optimize_prompt is not called."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        result_obj = _png_generation_result(
            prompt_used="a cat",
            generation_time=1.0,
            model_used="test/model",
            had_reference=False,
        )
        mock_generate.return_value = result_obj

        out_file = tmp_path / "out.png"
        result = _run_cli("--prompt", "a cat", "--no-optimize", "--out", str(out_file))

        assert result.exit_code == 0
        mock_validate.assert_called_once_with("a cat")
        mock_optimize.assert_not_called()
        mock_generate.assert_called_once()
        call_args, call_kw = mock_generate.call_args[0], mock_generate.call_args[1]
        assert call_args[0] == "a cat"
        assert call_kw.get("reference_images_b64") is None
        _assert_saved_png_cli_metadata(
            out_file,
            description="a cat",
            provider="openrouter",
            optimized=False,
            cli="generate",
        )
        assert b"genimg_meta_version" not in result_obj.image_data

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_reference_passed_to_generate(
        self,
        mock_config_cls: MagicMock,
        mock_ref: MagicMock,
        _mock_validate: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """With --reference, process_reference_image is called and result passed to generate_image."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        config.optimization_enabled = True
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        mock_ref.return_value = ("base64data", "hash123")
        mock_optimize.return_value = "optimized prompt"

        result_obj = _png_generation_result(
            prompt_used="optimized prompt",
            generation_time=1.0,
            model_used="test/model",
            had_reference=True,
        )
        mock_generate.return_value = result_obj

        ref_file = tmp_path / "ref.png"
        ref_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        out_file = tmp_path / "out.png"

        result = _run_cli(
            "--prompt",
            "a cat",
            "--reference",
            str(ref_file),
            "--out",
            str(out_file),
        )

        assert result.exit_code == 0
        mock_ref.assert_called_once()
        assert mock_ref.call_args[1]["config"] == config
        call_args, call_kw = mock_generate.call_args[0], mock_generate.call_args[1]
        assert call_args[0] == "optimized prompt"
        assert call_kw["reference_images_b64"] == ["base64data"]
        _assert_saved_png_cli_metadata(
            out_file,
            description="optimized prompt",
            provider="openrouter",
            optimized=True,
            cli="generate",
            had_reference=True,
            original_prompt="a cat",
        )

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_provider_ollama_passed_to_generate(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        _mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """--provider ollama is passed to generate_image."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        result_obj = _png_generation_result(prompt_used="a cat")
        mock_generate.return_value = result_obj

        out_file = tmp_path / "out.png"
        result = _run_cli(
            "--prompt", "a cat", "--no-optimize", "--provider", "ollama", "--out", str(out_file)
        )

        assert result.exit_code == 0
        mock_generate.assert_called_once()
        call_kw = mock_generate.call_args[1]
        assert call_kw.get("provider") == "ollama"
        _assert_saved_png_cli_metadata(
            out_file,
            description="a cat",
            provider="ollama",
            optimized=False,
            cli="generate",
        )

    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_provider_ollama_with_reference_raises(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        _mock_optimize: MagicMock,
        tmp_path: Path,
    ) -> None:
        """--provider ollama with --reference fails with ValidationError before process_reference_image."""
        config = MagicMock()
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        ref_file = tmp_path / "ref.png"
        ref_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        result = _run_cli("--prompt", "a cat", "--provider", "ollama", "--reference", str(ref_file))

        assert result.exit_code != 0
        assert "reference" in result.output.lower() or "Reference" in result.output
        assert "ollama" in result.output.lower()
        _mock_ref.assert_not_called()

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.unload_describe_models")
    @patch("genimg.cli.commands.get_description")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_use_reference_description_ollama_unloads_and_does_not_send_ref(
        self,
        mock_config_cls: MagicMock,
        mock_process_ref: MagicMock,
        _mock_validate: MagicMock,
        mock_get_description: MagicMock,
        mock_unload: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """With --use-reference-description and --provider ollama: unload_describe_models called, ref image not sent."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "ollama"
        config.default_optimization_model = "llama3.2"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        ref_file = tmp_path / "ref.png"
        ref_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        out_file = tmp_path / "out.png"
        mock_process_ref.return_value = ("b64data", "hash123")
        mock_get_description.return_value = "a fluffy cat"
        mock_optimize.return_value = "optimized prompt"
        result_obj = _png_generation_result(
            prompt_used="optimized prompt",
            had_reference=False,
        )
        mock_generate.return_value = result_obj

        result = _run_cli(
            "--prompt",
            "a cat",
            "--reference",
            str(ref_file),
            "--use-reference-description",
            "--provider",
            "ollama",
            "--out",
            str(out_file),
        )

        assert result.exit_code == 0
        mock_get_description.assert_called_once()
        call_kw = mock_get_description.call_args[1]
        assert call_kw.get("method") == "prose"
        assert call_kw.get("verbosity") == "detailed"
        mock_unload.assert_called_once()
        mock_optimize.assert_called_once()
        opt_kw = mock_optimize.call_args[1]
        assert opt_kw.get("reference_description") == "a fluffy cat"
        mock_generate.assert_called_once()
        assert mock_generate.call_args[1].get("reference_images_b64") is None
        _assert_saved_png_cli_metadata(
            out_file,
            description="optimized prompt",
            provider="ollama",
            optimized=True,
            cli="generate",
            original_prompt="a cat",
        )

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_out_used_for_writing(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        _mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """--out path is used to write image bytes."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        out_file = tmp_path / "custom.png"
        result_obj = _png_generation_result(
            prompt_used="x",
            generation_time=0.5,
        )
        mock_generate.return_value = result_obj

        result = _run_cli("--prompt", "x", "--no-optimize", "--out", str(out_file))

        assert result.exit_code == 0
        _assert_saved_png_cli_metadata(
            out_file,
            description="x",
            provider="openrouter",
            optimized=False,
            cli="generate",
        )
        assert str(out_file) in result.output

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_default_path_when_out_omitted(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        _mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When --out is omitted, default path uses ``--format`` (default webp)."""
        config = MagicMock()
        config.default_image_model = "test/model"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        result_obj = _jpeg_generation_result()
        mock_generate.return_value = result_obj

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", "--prompt", "x", "--no-optimize"])

        assert result.exit_code == 0
        webp_paths = list(tmp_path.glob("genimg_*.webp"))
        assert len(webp_paths) == 1
        saved = webp_paths[0].read_bytes()
        assert saved[:4] == b"RIFF" and saved[8:12] == b"WEBP"
        mock_generate.assert_called_once()
        assert "genimg_" in result.output and ".webp" in result.output

    @patch("genimg.cli.commands.Config")
    def test_validation_error_exit_code(
        self,
        mock_config_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """ValidationError from validate_prompt leads to exit code 2."""
        config = MagicMock()
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        with patch("genimg.cli.commands.validate_prompt") as mock_validate:
            mock_validate.side_effect = ValidationError("Prompt cannot be empty", field="prompt")

            result = _run_cli("--prompt", "x", "--no-optimize", "--out", str(tmp_path / "out.png"))

        assert result.exit_code == 2
        assert "Prompt" in result.output or "empty" in result.output

    @patch("genimg.cli.commands.Config")
    def test_configuration_error_exit_code(
        self,
        mock_config_cls: MagicMock,
    ) -> None:
        """ConfigurationError from config.validate leads to exit code 2."""
        config = MagicMock()
        mock_config_cls.from_env.return_value = config
        config.validate.side_effect = ConfigurationError("OpenRouter API key is required.")

        result = _run_cli("--prompt", "a cat", "--no-optimize", "--out", "/tmp/out.png")

        assert result.exit_code == 2
        assert "API key" in result.output or "required" in result.output

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_api_error_exit_code(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        _mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """APIError from generate_image leads to exit code 1."""
        config = MagicMock()
        config.default_image_model = "test/model"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_generate.side_effect = APIError("Model not found")

        result = _run_cli("--prompt", "x", "--no-optimize", "--out", str(tmp_path / "out.png"))

        assert result.exit_code == 1
        assert "Model" in result.output or "error" in result.output.lower()

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_cancellation_error_exit_code_130(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        _mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """CancellationError leads to exit code 130."""
        config = MagicMock()
        config.default_image_model = "test/model"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_generate.side_effect = CancellationError("Image generation was cancelled.")

        result = _run_cli("--prompt", "x", "--no-optimize", "--out", str(tmp_path / "out.png"))

        assert result.exit_code == 130
        assert "Cancelled" in result.output

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_quiet_only_prints_path(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """With --quiet, only the output path is printed (no progress or time)."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        config.optimization_enabled = True
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_optimize.return_value = "optimized"

        result_obj = _png_generation_result(
            prompt_used="optimized",
            generation_time=1.5,
        )
        mock_generate.return_value = result_obj

        out_file = tmp_path / "q.png"
        result = _run_cli("--prompt", "x", "--out", str(out_file), "--quiet")

        assert result.exit_code == 0
        # With --quiet we only echo the path once (to stdout), no "Optimizing…", "Generating…", "Saved to", "Generation time"
        lines = [line.strip() for line in result.output.strip().splitlines()]
        assert len(lines) == 1
        assert lines[0] == str(out_file)

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_save_prompt_writes_optimized_prompt(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """With --save-prompt, the optimized prompt is saved to the specified file."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        config.optimization_enabled = True
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        mock_optimize.return_value = "This is the optimized prompt with lots of detail."

        long_prompt = "This is the optimized prompt with lots of detail."
        result_obj = _png_generation_result(prompt_used=long_prompt)
        mock_generate.return_value = result_obj

        out_file = tmp_path / "out.png"
        prompt_file = tmp_path / "prompts" / "saved.txt"

        result = _run_cli(
            "--prompt",
            "a cat",
            "--out",
            str(out_file),
            "--save-prompt",
            str(prompt_file),
        )

        assert result.exit_code == 0
        # Check prompt file was created with parent directory
        assert prompt_file.exists()
        assert (
            prompt_file.read_text(encoding="utf-8")
            == "This is the optimized prompt with lots of detail."
        )
        # Check success message was shown
        assert "Saved optimized prompt" in result.output

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_save_prompt_not_used_with_no_optimize(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """With --no-optimize and --save-prompt, no prompt file is created."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        result_obj = _png_generation_result(prompt_used="a cat")
        mock_generate.return_value = result_obj

        out_file = tmp_path / "out.png"
        prompt_file = tmp_path / "prompt.txt"

        result = _run_cli(
            "--prompt",
            "a cat",
            "--no-optimize",
            "--out",
            str(out_file),
            "--save-prompt",
            str(prompt_file),
        )

        assert result.exit_code == 0
        # Optimization was skipped, so no prompt file should be created
        assert not prompt_file.exists()
        mock_optimize.assert_not_called()

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_save_prompt_error_does_not_fail_generation(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """If saving the prompt fails, a warning is shown but generation proceeds."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        config.optimization_enabled = True
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        mock_optimize.return_value = "optimized prompt"

        result_obj = _png_generation_result(prompt_used="optimized prompt")
        mock_generate.return_value = result_obj

        out_file = tmp_path / "out.png"
        # Use a path that will fail to write (read-only parent)
        bad_prompt_file = Path("/nonexistent/directory/prompt.txt")

        result = _run_cli(
            "--prompt",
            "a cat",
            "--out",
            str(out_file),
            "--save-prompt",
            str(bad_prompt_file),
        )

        # Generation should succeed despite prompt save failure
        assert result.exit_code == 0
        assert out_file.exists()
        # Warning should be shown
        assert "Could not save prompt" in result.output or "Warning" in result.output

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_api_key_option_overrides_config(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        _mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """--api-key option overrides the API key from environment."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        config.set_api_key = MagicMock()

        result_obj = _png_generation_result(prompt_used="a cat")
        mock_generate.return_value = result_obj

        out_file = tmp_path / "out.png"
        test_api_key = "sk-or-v1-test-key-12345"

        result = _run_cli(
            "--prompt",
            "a cat",
            "--no-optimize",
            "--out",
            str(out_file),
            "--api-key",
            test_api_key,
        )

        assert result.exit_code == 0
        # Verify set_api_key was called with the provided key
        config.set_api_key.assert_called_once_with(test_api_key)
        # Verify validate was still called after setting the key
        config.validate.assert_called_once()

    @patch("genimg.cli.commands.Config")
    def test_api_key_option_without_env_var(
        self,
        mock_config_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """--api-key allows generation even when OPENROUTER_API_KEY env var is not set."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        config.openrouter_api_key = ""  # Simulate no env var
        mock_config_cls.from_env.return_value = config
        config.set_api_key = MagicMock()
        config.validate.return_value = None

        with patch("genimg.cli.commands.generate_image") as mock_generate:
            result_obj = _png_generation_result(prompt_used="test")
            mock_generate.return_value = result_obj

            out_file = tmp_path / "out.png"
            test_api_key = "sk-or-v1-override-key"

            result = _run_cli(
                "--prompt",
                "test",
                "--no-optimize",
                "--out",
                str(out_file),
                "--api-key",
                test_api_key,
            )

            assert result.exit_code == 0
            # Verify the API key was set before validation
            config.set_api_key.assert_called_once_with(test_api_key)
            config.validate.assert_called_once()

    @patch("genimg.cli.commands.configure_logging")
    @patch("genimg.cli.commands.get_verbosity_from_env", return_value=0)
    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_verbose_flag_calls_configure_logging(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        _mock_optimize: MagicMock,
        _mock_generate: MagicMock,
        mock_get_verbosity: MagicMock,
        mock_configure_logging: MagicMock,
        tmp_path: Path,
    ) -> None:
        """-v and -vv call configure_logging with verbose_level 1 and 2."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        result_obj = _png_generation_result(prompt_used="x")
        _mock_generate.return_value = result_obj
        out_file = tmp_path / "out.png"

        result = _run_cli("--prompt", "x", "--no-optimize", "--out", str(out_file), "-v")
        assert result.exit_code == 0
        mock_configure_logging.assert_called_once()
        call_kw = mock_configure_logging.call_args[1]
        assert call_kw["verbose_level"] == 1
        assert call_kw["quiet"] is False

        mock_configure_logging.reset_mock()
        mock_get_verbosity.return_value = 0
        result2 = _run_cli("--prompt", "x", "--no-optimize", "--out", str(out_file), "-v", "-v")
        assert result2.exit_code == 0
        mock_configure_logging.assert_called_once()
        call_kw2 = mock_configure_logging.call_args[1]
        assert call_kw2["verbose_level"] == 2
        assert call_kw2["quiet"] is False

    @patch("genimg.cli.commands.configure_logging")
    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_quiet_calls_configure_logging_with_quiet_true(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        _mock_optimize: MagicMock,
        _mock_generate: MagicMock,
        mock_configure_logging: MagicMock,
        tmp_path: Path,
    ) -> None:
        """--quiet calls configure_logging(..., quiet=True)."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        result_obj = _png_generation_result(prompt_used="x")
        _mock_generate.return_value = result_obj
        out_file = tmp_path / "out.png"

        result = _run_cli("--prompt", "x", "--no-optimize", "--out", str(out_file), "--quiet")
        assert result.exit_code == 0
        mock_configure_logging.assert_called_once()
        call_kw = mock_configure_logging.call_args[1]
        assert call_kw["quiet"] is True

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_format_webp_replaces_out_extension(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        config.optimization_enabled = True
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_optimize.return_value = "optimized"
        result_obj = _png_generation_result(prompt_used="optimized")
        mock_generate.return_value = result_obj

        dest = tmp_path / "sub" / "bar.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "generate",
                "--prompt",
                "x",
                "--format",
                "webp",
                "--out",
                str(dest),
            ],
        )
        assert result.exit_code == 0
        coerced = tmp_path / "sub" / "bar.webp"
        assert coerced.exists()
        assert not dest.exists()
        assert str(coerced) in result.output

    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.optimize_prompt")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.Config")
    def test_format_jpg_writes_jpeg_with_exif(
        self,
        mock_config_cls: MagicMock,
        _mock_ref: MagicMock,
        _mock_validate: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from PIL.ExifTags import Base

        config = MagicMock()
        config.default_image_model = "test/model"
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_optimize.return_value = "opt"
        result_obj = _png_generation_result(prompt_used="opt")
        mock_generate.return_value = result_obj

        out = tmp_path / "x.webp"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "generate",
                "--prompt",
                "a",
                "--no-optimize",
                "--format",
                "jpg",
                "--out",
                str(out),
            ],
        )
        assert result.exit_code == 0
        jpg = tmp_path / "x.jpg"
        assert jpg.exists()
        ex = Image.open(jpg).getexif()
        assert ex.get(Base.Software, "").startswith("genimg ")
        uc = ex.get(Base.UserComment)
        assert isinstance(uc, bytes) and b"genimg_meta_version" in uc
        assert str(jpg) in result.output


@pytest.mark.unit
class TestCharacterCommand:
    @patch("genimg.cli.commands.progress.print_success_result")
    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.Config")
    def test_pins_openrouter_and_default_model_when_flags_omitted(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        mock_process_ref: MagicMock,
        mock_generate: MagicMock,
        mock_print_success: MagicMock,
        tmp_path: Path,
    ) -> None:
        config = MagicMock()
        config.default_image_provider = "ollama"
        config.default_image_model = "some/other-model"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        mock_process_ref.return_value = ("b64x", "h1")
        result_obj = _png_generation_result(
            prompt_used="x",
            generation_time=1.2,
            model_used=DEFAULT_IMAGE_MODEL,
            had_reference=True,
        )
        mock_generate.return_value = result_obj

        ref = tmp_path / "a.png"
        ref.write_bytes(b"\x89PNG\r\n\x1a\n")
        out = tmp_path / "out.png"

        result = _run_character("T", str(ref), "--quiet", "--out", str(out))
        assert result.exit_code == 0
        mock_print_success.assert_not_called()
        kw = mock_generate.call_args[1]
        assert kw["provider"] == "openrouter"
        assert kw["model"] == DEFAULT_IMAGE_MODEL
        assert kw["reference_images_b64"] == ["b64x"]
        _assert_saved_png_cli_metadata(
            out,
            description="x",
            provider="openrouter",
            optimized=False,
            cli="character",
            had_reference=True,
        )

    @patch("genimg.cli.commands.progress.print_success_result")
    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.Config")
    def test_composed_prompt_and_multi_refs(
        self,
        mock_config_cls: MagicMock,
        mock_validate: MagicMock,
        mock_process_ref: MagicMock,
        mock_generate: MagicMock,
        mock_print_success: MagicMock,
        tmp_path: Path,
    ) -> None:
        config = MagicMock()
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        b64_j = base64.b64encode(_CLI_MINIMAL_JPEG).decode("ascii")
        mock_process_ref.side_effect = [(b64_j, "h1"), (b64_j, "h2")]
        composed = CHARACTER_TURNAROUND_PROMPT + (
            "\n\nadd a hat\n\nThe attached reference is a horizontal strip of multiple photos of "
            "the same person; use every segment for consistent likeness."
        )
        result_obj = _png_generation_result(
            prompt_used=composed,
            generation_time=0.5,
            model_used=DEFAULT_IMAGE_MODEL,
            had_reference=True,
        )
        mock_generate.return_value = result_obj

        r1 = tmp_path / "r1.png"
        r2 = tmp_path / "r2.png"
        r1.write_bytes(b"\x89PNG\r\n\x1a\n")
        r2.write_bytes(b"\x89PNG\r\n\x1a\n")
        out = tmp_path / "o.png"

        result = _run_character(
            "Hero",
            str(r1),
            str(r2),
            "--prompt",
            "add a hat",
            "--quiet",
            "--out",
            str(out),
        )
        assert result.exit_code == 0
        mock_print_success.assert_not_called()
        sent_prompt = mock_generate.call_args[0][0]
        assert sent_prompt.startswith(CHARACTER_TURNAROUND_PROMPT)
        assert "add a hat" in sent_prompt
        assert "horizontal strip" in sent_prompt
        mock_validate.assert_called_once_with(sent_prompt)
        refs_sent = mock_generate.call_args[1]["reference_images_b64"]
        assert refs_sent is not None and len(refs_sent) == 1
        assert refs_sent[0] == merge_jpeg_base64_references_horizontally([b64_j, b64_j])
        _assert_saved_png_cli_metadata(
            out,
            description=composed,
            provider="openrouter",
            optimized=False,
            cli="character",
            had_reference=True,
            user_prompt="add a hat",
        )

    @patch("genimg.cli.commands.Config")
    def test_provider_ollama_fails_before_generate(
        self,
        mock_config_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        config = MagicMock()
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        ref = tmp_path / "r.png"
        ref.write_bytes(b"\x89PNG\r\n\x1a\n")

        result = _run_character(
            "T", str(ref), "--provider", "ollama", "--quiet", "--out", str(tmp_path / "o.png")
        )
        assert result.exit_code != 0
        assert "reference" in result.output.lower()

    @patch("genimg.cli.commands.progress.print_success_result")
    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.Config")
    def test_stderr_variation_c_and_stdout_path_only(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        mock_process_ref: MagicMock,
        mock_generate: MagicMock,
        mock_print_success: MagicMock,
        tmp_path: Path,
    ) -> None:
        config = MagicMock()
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_process_ref.return_value = ("b64", "h")
        result_obj = _png_generation_result(
            prompt_used="p",
            generation_time=2.0,
            model_used=DEFAULT_IMAGE_MODEL,
            had_reference=True,
        )
        mock_generate.return_value = result_obj

        ref = tmp_path / "front.png"
        ref.write_bytes(b"\x89PNG\r\n\x1a\n")
        out = tmp_path / "saved.png"

        result = _run_character("My │Title", str(ref), "--out", str(out))
        assert result.exit_code == 0
        mock_print_success.assert_not_called()
        combined = result.output
        assert "genimg character" in combined
        assert "refs=" in combined
        assert "refs:" in combined
        assert "user:" in combined
        assert "gen:" in combined
        lines = [ln for ln in combined.strip().splitlines() if ln.strip()]
        assert lines[-1] == str(out.resolve())
        _assert_saved_png_cli_metadata(
            out,
            description="p",
            provider="openrouter",
            optimized=False,
            cli="character",
            had_reference=True,
        )

    @patch("genimg.cli.commands.progress.print_success_result")
    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.Config")
    def test_quiet_suppresses_variation_c_lines(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        mock_process_ref: MagicMock,
        mock_generate: MagicMock,
        mock_print_success: MagicMock,
        tmp_path: Path,
    ) -> None:
        config = MagicMock()
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_process_ref.return_value = ("b64", "h")
        result_obj = _png_generation_result(
            prompt_used="p",
            generation_time=1.0,
            model_used=DEFAULT_IMAGE_MODEL,
            had_reference=True,
        )
        mock_generate.return_value = result_obj

        ref = tmp_path / "r.png"
        ref.write_bytes(b"\x89PNG\r\n\x1a\n")
        out = tmp_path / "o.png"

        result = _run_character("T", str(ref), "--quiet", "--out", str(out))
        assert result.exit_code == 0
        mock_print_success.assert_not_called()
        combined = result.output
        assert "genimg character" not in combined
        assert "refs:" not in combined
        lines = [ln for ln in combined.strip().splitlines() if ln.strip()]
        assert lines[-1] == str(out.resolve())

    @patch("genimg.cli.commands.progress.print_success_result")
    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.Config")
    def test_output_alias_writes_same_as_out(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        mock_process_ref: MagicMock,
        mock_generate: MagicMock,
        mock_print_success: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        config = MagicMock()
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_process_ref.return_value = ("b64", "h")
        result_obj = _png_generation_result(
            prompt_used="p",
            generation_time=0.1,
            model_used=DEFAULT_IMAGE_MODEL,
            had_reference=True,
        )
        mock_generate.return_value = result_obj

        ref = tmp_path / "r.png"
        ref.write_bytes(b"\x89PNG\r\n\x1a\n")
        dest = tmp_path / "via-alias.png"
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["character", "--format", "png", "T", str(ref), "--quiet", "--output", str(dest)]
        )
        assert result.exit_code == 0
        _assert_saved_png_cli_metadata(
            dest,
            description="p",
            provider="openrouter",
            optimized=False,
            cli="character",
            had_reference=True,
        )

    @patch("genimg.cli.commands.character_default_output_path")
    @patch("genimg.cli.commands.progress.print_success_result")
    @patch("genimg.cli.commands.generate_image")
    @patch("genimg.cli.commands.process_reference_image")
    @patch("genimg.cli.commands.validate_prompt")
    @patch("genimg.cli.commands.Config")
    def test_default_output_uses_character_path_helper(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        mock_process_ref: MagicMock,
        mock_generate: MagicMock,
        mock_print_success: MagicMock,
        mock_char_path: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        config = MagicMock()
        config.default_image_provider = "openrouter"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_process_ref.return_value = ("b64", "h")
        result_obj = _jpeg_generation_result(
            prompt_used="p",
            generation_time=0.2,
            model_used=DEFAULT_IMAGE_MODEL,
            had_reference=True,
        )
        mock_generate.return_value = result_obj
        mock_char_path.return_value = "Stem-20260101_000000.webp"

        ref = tmp_path / "r.png"
        ref.write_bytes(b"\x89PNG\r\n\x1a\n")
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["character", "MyTitle", str(ref), "--quiet"])
        assert result.exit_code == 0
        mock_char_path.assert_called_once_with("MyTitle", "webp")
        webp_path = tmp_path / "Stem-20260101_000000.webp"
        data = webp_path.read_bytes()
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
