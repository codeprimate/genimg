"""Unit tests for the genimg CLI."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner, Result

from genimg.cli import cli
from genimg.utils.exceptions import (
    APIError,
    CancellationError,
    ConfigurationError,
    ValidationError,
)


def _run_cli(*args: str) -> Result:
    """Invoke genimg generate with given args; returns Click's Result."""
    runner = CliRunner()
    return runner.invoke(cli, ["generate", *args])


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

        result_obj = MagicMock()
        result_obj.image_data = b"\x89PNG\r\n\x1a\n"
        result_obj.format = "png"
        result_obj.generation_time = 1.0
        result_obj.model_used = "test/model"
        result_obj.prompt_used = "a cat"
        result_obj.had_reference = False
        mock_generate.return_value = result_obj

        out_file = tmp_path / "out.png"
        result = _run_cli("--prompt", "a cat", "--no-optimize", "--out", str(out_file))

        assert result.exit_code == 0
        mock_validate.assert_called_once_with("a cat")
        mock_optimize.assert_not_called()
        mock_generate.assert_called_once()
        call_args, call_kw = mock_generate.call_args[0], mock_generate.call_args[1]
        assert call_args[0] == "a cat"
        assert call_kw.get("reference_image_b64") is None
        assert out_file.read_bytes() == result_obj.image_data

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

        result_obj = MagicMock()
        result_obj.image_data = b"\x89PNG\r\n\x1a\n"
        result_obj.format = "png"
        result_obj.generation_time = 1.0
        result_obj.model_used = "test/model"
        result_obj.prompt_used = "optimized prompt"
        result_obj.had_reference = True
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
        assert call_kw["reference_image_b64"] == "base64data"

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

        result_obj = MagicMock()
        result_obj.image_data = b"\x89PNG\r\n\x1a\n"
        result_obj.format = "png"
        result_obj.generation_time = 1.0
        result_obj.model_used = "test/model"
        result_obj.prompt_used = "a cat"
        result_obj.had_reference = False
        mock_generate.return_value = result_obj

        out_file = tmp_path / "out.png"
        result = _run_cli(
            "--prompt", "a cat", "--no-optimize", "--provider", "ollama", "--out", str(out_file)
        )

        assert result.exit_code == 0
        mock_generate.assert_called_once()
        call_kw = mock_generate.call_args[1]
        assert call_kw.get("provider") == "ollama"

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
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        out_file = tmp_path / "custom.png"
        result_obj = MagicMock()
        result_obj.image_data = b"imagedata"
        result_obj.format = "png"
        result_obj.generation_time = 0.5
        result_obj.model_used = "test/model"
        result_obj.prompt_used = "x"
        result_obj.had_reference = False
        mock_generate.return_value = result_obj

        result = _run_cli("--prompt", "x", "--no-optimize", "--out", str(out_file))

        assert result.exit_code == 0
        assert out_file.read_bytes() == b"imagedata"
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
    ) -> None:
        """When --out is omitted, default path genimg_<timestamp>.<ext> is used."""
        config = MagicMock()
        config.default_image_model = "test/model"
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        result_obj = MagicMock()
        result_obj.image_data = b"imagedata"
        result_obj.format = "jpeg"
        result_obj.generation_time = 0.5
        result_obj.model_used = "test/model"
        result_obj.prompt_used = "x"
        result_obj.had_reference = False
        mock_generate.return_value = result_obj

        default_path = tmp_path / "genimg_20260207_120000.jpeg"
        with patch("genimg.cli.commands.default_output_path", return_value=str(default_path)):
            result = _run_cli("--prompt", "x", "--no-optimize")

        assert result.exit_code == 0
        assert default_path.exists()
        assert default_path.read_bytes() == b"imagedata"
        assert "genimg_" in result.output and ".jpeg" in result.output

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
        config.optimization_enabled = True
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_optimize.return_value = "optimized"

        result_obj = MagicMock()
        result_obj.image_data = b"data"
        result_obj.format = "png"
        result_obj.generation_time = 1.5
        result_obj.model_used = "test/model"
        result_obj.prompt_used = "optimized"
        result_obj.had_reference = False
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
        config.optimization_enabled = True
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        mock_optimize.return_value = "This is the optimized prompt with lots of detail."

        result_obj = MagicMock()
        result_obj.image_data = b"imagedata"
        result_obj.format = "png"
        result_obj.generation_time = 1.0
        result_obj.model_used = "test/model"
        result_obj.prompt_used = "This is the optimized prompt with lots of detail."
        result_obj.had_reference = False
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
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        result_obj = MagicMock()
        result_obj.image_data = b"imagedata"
        result_obj.format = "png"
        result_obj.generation_time = 1.0
        result_obj.model_used = "test/model"
        result_obj.prompt_used = "a cat"
        result_obj.had_reference = False
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
        config.optimization_enabled = True
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        mock_optimize.return_value = "optimized prompt"

        result_obj = MagicMock()
        result_obj.image_data = b"imagedata"
        result_obj.format = "png"
        result_obj.generation_time = 1.0
        result_obj.model_used = "test/model"
        result_obj.prompt_used = "optimized prompt"
        result_obj.had_reference = False
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
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        config.set_api_key = MagicMock()

        result_obj = MagicMock()
        result_obj.image_data = b"imagedata"
        result_obj.format = "png"
        result_obj.generation_time = 1.0
        result_obj.model_used = "test/model"
        result_obj.prompt_used = "a cat"
        result_obj.had_reference = False
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
        config.openrouter_api_key = ""  # Simulate no env var
        mock_config_cls.from_env.return_value = config
        config.set_api_key = MagicMock()
        config.validate.return_value = None

        with patch("genimg.cli.commands.generate_image") as mock_generate:
            result_obj = MagicMock()
            result_obj.image_data = b"imagedata"
            result_obj.format = "png"
            result_obj.generation_time = 1.0
            result_obj.model_used = "test/model"
            result_obj.prompt_used = "test"
            result_obj.had_reference = False
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
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        result_obj = MagicMock()
        result_obj.image_data = b"data"
        result_obj.format = "png"
        result_obj.generation_time = 1.0
        result_obj.model_used = "test/model"
        result_obj.prompt_used = "x"
        result_obj.had_reference = False
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
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        result_obj = MagicMock()
        result_obj.image_data = b"data"
        result_obj.format = "png"
        result_obj.generation_time = 1.0
        result_obj.model_used = "test/model"
        result_obj.prompt_used = "x"
        result_obj.had_reference = False
        _mock_generate.return_value = result_obj
        out_file = tmp_path / "out.png"

        result = _run_cli("--prompt", "x", "--no-optimize", "--out", str(out_file), "--quiet")
        assert result.exit_code == 0
        mock_configure_logging.assert_called_once()
        call_kw = mock_configure_logging.call_args[1]
        assert call_kw["quiet"] is True
