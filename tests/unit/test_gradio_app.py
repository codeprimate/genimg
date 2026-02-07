"""Unit tests for the Gradio UI (gradio_app)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from genimg.ui import gradio_app
from genimg.utils.exceptions import (
    APIError,
    CancellationError,
    ConfigurationError,
    ImageProcessingError,
    ValidationError,
)


@pytest.mark.unit
class TestExceptionToMessage:
    """Test exception-to-user-message mapping."""

    def test_validation_error(self) -> None:
        msg = gradio_app._exception_to_message(ValidationError("Bad prompt", field="prompt"))
        assert "Bad prompt" in msg
        assert "prompt" in msg

    def test_configuration_error(self) -> None:
        msg = gradio_app._exception_to_message(ConfigurationError("Missing API key"))
        assert msg == "Missing API key"

    def test_cancellation_error(self) -> None:
        msg = gradio_app._exception_to_message(CancellationError("Cancelled."))
        assert msg == "Cancelled."

    def test_api_error(self) -> None:
        msg = gradio_app._exception_to_message(APIError("Rate limit exceeded"))
        assert msg == "Rate limit exceeded"

    def test_image_processing_error(self) -> None:
        msg = gradio_app._exception_to_message(ImageProcessingError("Invalid format"))
        assert msg == "Invalid format"


@pytest.mark.unit
class TestReferenceSourceForProcess:
    """Test reference image value handling from Gradio."""

    def test_none(self) -> None:
        assert gradio_app._reference_source_for_process(None) is None

    def test_empty_string(self) -> None:
        assert gradio_app._reference_source_for_process("") is None
        assert gradio_app._reference_source_for_process("   ") is None

    def test_path_string(self) -> None:
        assert gradio_app._reference_source_for_process("/tmp/ref.png") == "/tmp/ref.png"

    def test_dict_with_path(self) -> None:
        assert gradio_app._reference_source_for_process({"path": "/tmp/x.jpg"}) == "/tmp/x.jpg"
        assert gradio_app._reference_source_for_process({"url": "/tmp/y.png"}) == "/tmp/y.png"

    def test_dict_with_data_url(self) -> None:
        """Dict with url as data URL is passed through for process_reference_image."""
        data_url = "data:image/png;base64,iVBORw0KGgo="
        assert gradio_app._reference_source_for_process({"url": data_url}) == data_url

    def test_pil_image_returns_path(self) -> None:
        """PIL Image from Gradio is saved to temp file and path returned."""
        pil = Image.new("RGB", (2, 2), color="red")
        out = gradio_app._reference_source_for_process(pil)
        assert out is not None
        assert isinstance(out, str)
        assert out.endswith(".png")
        assert Path(out).is_file()
        Path(out).unlink()


@pytest.mark.unit
class TestRunGenerate:
    """Test _run_generate with mocked library."""

    @patch("genimg.ui.gradio_app.generate_image")
    @patch("genimg.ui.gradio_app.optimize_prompt")
    @patch("genimg.ui.gradio_app.process_reference_image")
    @patch("genimg.ui.gradio_app.validate_prompt")
    @patch("genimg.ui.gradio_app.Config")
    def test_empty_prompt_returns_message(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        _mock_ref: MagicMock,
        _mock_optimize: MagicMock,
        _mock_generate: MagicMock,
    ) -> None:
        status, img, msg = gradio_app._run_generate("", True, None, None)
        assert img is None
        assert "prompt" in msg.lower() or "Enter" in msg
        _mock_validate.assert_not_called()
        _mock_generate.assert_not_called()

    @patch("genimg.ui.gradio_app.generate_image")
    @patch("genimg.ui.gradio_app.optimize_prompt")
    @patch("genimg.ui.gradio_app.process_reference_image")
    @patch("genimg.ui.gradio_app.validate_prompt")
    @patch("genimg.ui.gradio_app.Config")
    def test_no_optimize_calls_generate_only(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        _mock_ref: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        config = MagicMock()
        config.default_image_model = "test/model"
        config.openrouter_api_key = "sk-test"
        config.generation_timeout = 60
        config.max_image_pixels = 2_000_000
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        pil_image = Image.new("RGB", (10, 10), color="red")
        result = MagicMock()
        result.image = pil_image
        result.generation_time = 1.5
        mock_generate.return_value = result

        status, img_path, msg = gradio_app._run_generate("a cat", False, None, None)
        mock_optimize.assert_not_called()
        mock_generate.assert_called_once()
        call_kw = mock_generate.call_args[1]
        assert call_kw.get("reference_image_b64") is None
        assert "Done" in msg
        assert img_path is not None
        assert img_path.endswith(".jpg")

    @patch("genimg.ui.gradio_app.generate_image")
    @patch("genimg.ui.gradio_app.optimize_prompt")
    @patch("genimg.ui.gradio_app.process_reference_image")
    @patch("genimg.ui.gradio_app.validate_prompt")
    @patch("genimg.ui.gradio_app.Config")
    def test_optimize_on_calls_optimize_then_generate(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        _mock_ref: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        config = MagicMock()
        config.default_image_model = "test/model"
        config.openrouter_api_key = "sk-test"
        config.generation_timeout = 60
        config.max_image_pixels = 2_000_000
        config.optimization_enabled = False
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_optimize.return_value = "optimized prompt"

        pil_image = Image.new("RGB", (10, 10), color="blue")
        result = MagicMock()
        result.image = pil_image
        result.generation_time = 2.0
        mock_generate.return_value = result

        status, img_path, msg = gradio_app._run_generate("a dog", True, None, None)
        mock_optimize.assert_called_once()
        mock_generate.assert_called_once()
        assert mock_generate.call_args[0][0] == "optimized prompt"

    @patch("genimg.ui.gradio_app.generate_image")
    @patch("genimg.ui.gradio_app.optimize_prompt")
    @patch("genimg.ui.gradio_app.process_reference_image")
    @patch("genimg.ui.gradio_app.validate_prompt")
    @patch("genimg.ui.gradio_app.Config")
    def test_reference_passed_to_optimize_and_generate(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        mock_ref: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        ref_path = str(tmp_path / "ref.jpg")
        (tmp_path / "ref.jpg").write_bytes(b"\xff\xd8\xff")  # minimal JPEG magic
        config = MagicMock()
        config.default_image_model = "test/model"
        config.openrouter_api_key = "sk-test"
        config.generation_timeout = 60
        config.max_image_pixels = 2_000_000
        config.optimization_enabled = False
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_ref.return_value = ("base64data", "hash123")
        mock_optimize.return_value = "optimized"
        pil_image = Image.new("RGB", (10, 10), color="green")
        result = MagicMock()
        result.image = pil_image
        result.generation_time = 1.0
        mock_generate.return_value = result

        status, img_path, msg = gradio_app._run_generate("a tree", True, ref_path, None)
        mock_ref.assert_called_once()
        mock_optimize.assert_called_once()
        assert mock_optimize.call_args[1].get("reference_hash") == "hash123"
        assert mock_generate.call_args[1].get("reference_image_b64") == "base64data"

    @patch("genimg.ui.gradio_app.generate_image")
    @patch("genimg.ui.gradio_app.optimize_prompt")
    @patch("genimg.ui.gradio_app.process_reference_image")
    @patch("genimg.ui.gradio_app.validate_prompt")
    @patch("genimg.ui.gradio_app.Config")
    def test_configuration_error_returned_as_message(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        _mock_ref: MagicMock,
        _mock_optimize: MagicMock,
        _mock_generate: MagicMock,
    ) -> None:
        mock_config_cls.from_env.return_value.validate.side_effect = ConfigurationError(
            "Missing API key"
        )
        status, img_path, msg = gradio_app._run_generate("hello", False, None, None)
        assert img_path is None
        assert "API key" in msg or "Missing" in msg

    @patch("genimg.ui.gradio_app.generate_image")
    @patch("genimg.ui.gradio_app.optimize_prompt")
    @patch("genimg.ui.gradio_app.process_reference_image")
    @patch("genimg.ui.gradio_app.validate_prompt")
    @patch("genimg.ui.gradio_app.Config")
    def test_cancellation_error_returned_as_message(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        _mock_ref: MagicMock,
        mock_optimize: MagicMock,
        _mock_generate: MagicMock,
    ) -> None:
        config = MagicMock()
        config.default_image_model = "test/model"
        config.openrouter_api_key = "sk-test"
        config.generation_timeout = 60
        config.max_image_pixels = 2_000_000
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_optimize.side_effect = CancellationError("Cancelled.")
        status, img_path, msg = gradio_app._run_generate("hello", True, None, None)
        assert img_path is None
        assert "Cancelled" in msg

    @patch("genimg.ui.gradio_app.generate_image")
    @patch("genimg.ui.gradio_app.optimize_prompt")
    @patch("genimg.ui.gradio_app.process_reference_image")
    @patch("genimg.ui.gradio_app.validate_prompt")
    @patch("genimg.ui.gradio_app.Config")
    def test_optimized_box_used_when_non_empty_skips_optimize(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        _mock_ref: MagicMock,
        mock_optimize: MagicMock,
        mock_generate: MagicMock,
    ) -> None:
        """When Optimized prompt box has content, Generate uses it and does not run optimize."""
        config = MagicMock()
        config.default_image_model = "test/model"
        config.openrouter_api_key = "sk-test"
        config.generation_timeout = 60
        config.max_image_pixels = 2_000_000
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None

        pil_image = Image.new("RGB", (10, 10), color="red")
        result = MagicMock()
        result.image = pil_image
        result.generation_time = 1.0
        mock_generate.return_value = result

        stream = gradio_app._run_generate_stream(
            "original prompt",
            optimize=True,
            optimized_prompt_value="user edited prompt",
            reference_value=None,
            model=None,
        )
        items = list(stream)
        mock_optimize.assert_not_called()
        mock_generate.assert_called_once()
        assert mock_generate.call_args[0][0] == "user edited prompt"
        assert any("Done" in (item[0] or "") for item in items)


@pytest.mark.unit
class TestGenerateClickHandler:
    """Test _generate_click_handler (UI handler with mocked stream)."""

    def test_handler_yields_from_stream(self) -> None:
        """Handler yields status, image, and button updates from stream."""
        gradio_app._cancel_event.clear()
        with patch("genimg.ui.gradio_app._run_generate_stream") as mock_stream:
            mock_stream.return_value = iter(
                [
                    ("Generating…", None, False, True, ""),
                    ("Done in 1.0s", "/tmp/123.jpg", True, False, ""),
                ]
            )
            out = list(gradio_app._generate_click_handler("a cat", False, "", None, None, None))
        assert len(out) == 2
        assert out[0][0] == "Generating…"
        assert out[1][0] == "Done in 1.0s"
        assert out[1][1] == "/tmp/123.jpg"

    def test_handler_on_genimg_error_yields_message_and_preserves_opt_text(self) -> None:
        """On GenimgError, handler yields error message and preserves optimized prompt box."""
        gradio_app._cancel_event.clear()
        with patch("genimg.ui.gradio_app._run_generate_stream") as mock_stream:
            mock_stream.side_effect = ConfigurationError("Bad config")
            out = list(
                gradio_app._generate_click_handler("x", True, "edited prompt", None, None, None)
            )
        assert len(out) == 1
        assert "config" in out[0][0].lower() or "Bad" in out[0][0]
        assert out[0][4] == "edited prompt"

    def test_handler_on_generic_exception_yields_string(self) -> None:
        gradio_app._cancel_event.clear()
        with patch("genimg.ui.gradio_app._run_generate_stream") as mock_stream:
            mock_stream.side_effect = RuntimeError("oops")
            out = list(gradio_app._generate_click_handler("x", False, "", None, None, None))
        assert len(out) == 1
        assert "oops" in out[0][0]


@pytest.mark.unit
class TestOptimizeClickHandler:
    """Test _optimize_click_handler (UI handler with mocked stream)."""

    def test_handler_yields_from_stream(self) -> None:
        gradio_app._cancel_event.clear()
        with patch("genimg.ui.gradio_app._run_optimize_only_stream") as mock_stream:
            mock_stream.return_value = iter(
                [
                    ("Optimizing…", "", False, True, False),
                    ("Done.", "optimized text", True, False, True),
                ]
            )
            out = list(gradio_app._optimize_click_handler("a dog", None, None))
        assert len(out) == 2
        assert out[1][1] == "optimized text"

    def test_handler_on_error_yields_message(self) -> None:
        gradio_app._cancel_event.clear()
        with patch("genimg.ui.gradio_app._run_optimize_only_stream") as mock_stream:
            mock_stream.side_effect = APIError("Ollama failed")
            out = list(gradio_app._optimize_click_handler("x", None, None))
        assert len(out) == 1
        assert "Ollama" in out[0][0] or "failed" in out[0][0]
        assert out[0][1] == ""


@pytest.mark.unit
class TestStopAndPromptHandlers:
    """Test _stop_click_handler and _prompt_change_handler."""

    def test_stop_click_sets_event_and_returns_updates(self) -> None:
        gradio_app._cancel_event.clear()
        a, b = gradio_app._stop_click_handler()
        assert gradio_app._cancel_event.is_set()
        assert a is not None and b is not None

    def test_prompt_change_empty_disabled(self) -> None:
        a, b = gradio_app._prompt_change_handler("")
        assert a["interactive"] is False
        assert b["interactive"] is False

    def test_prompt_change_non_empty_enabled(self) -> None:
        a, b = gradio_app._prompt_change_handler("hello")
        assert a["interactive"] is True
        assert b["interactive"] is True


@pytest.mark.unit
class TestBuildBlocksAndLaunch:
    """Test _build_blocks and launch (build UI, no server)."""

    def test_build_blocks_returns_blocks(self) -> None:
        app = gradio_app._build_blocks()
        assert app is not None

    def test_launch_calls_build_and_launch(self) -> None:
        """launch() builds app and calls app.launch with host/port/share."""
        with patch("genimg.ui.gradio_app._build_blocks") as mock_build:
            mock_app = MagicMock()
            mock_build.return_value = mock_app
            gradio_app.launch(server_name="0.0.0.0", server_port=9999, share=True)
            mock_build.assert_called_once()
            mock_app.launch.assert_called_once()
            call_kw = mock_app.launch.call_args[1]
            assert call_kw["server_name"] == "0.0.0.0"
            assert call_kw["server_port"] == 9999
            assert call_kw["share"] is True


@pytest.mark.unit
class TestMainEntryPoint:
    """Test main() entry point (genimg-ui --port etc.)."""

    def test_main_parses_port_and_calls_launch(self) -> None:
        """main() parses --port and passes it to launch()."""
        with patch("genimg.ui.gradio_app.launch") as mock_launch:
            with patch.object(sys, "argv", ["genimg-ui", "--port", "8888"]):
                gradio_app.main()
            mock_launch.assert_called_once()
            assert mock_launch.call_args[1]["server_port"] == 8888
            assert mock_launch.call_args[1]["server_name"] is None
            assert mock_launch.call_args[1]["share"] is False

    def test_main_parses_host_and_share(self) -> None:
        """main() parses --host and --share."""
        with patch("genimg.ui.gradio_app.launch") as mock_launch:
            with patch.object(
                sys, "argv", ["genimg-ui", "--port", "9000", "--host", "0.0.0.0", "--share"]
            ):
                gradio_app.main()
            mock_launch.assert_called_once()
            assert mock_launch.call_args[1]["server_port"] == 9000
            assert mock_launch.call_args[1]["server_name"] == "0.0.0.0"
            assert mock_launch.call_args[1]["share"] is True


@pytest.mark.unit
class TestRunOptimizeOnlyStream:
    """Test _run_optimize_only_stream (Optimize / Regenerate button)."""

    @patch("genimg.ui.gradio_app.optimize_prompt")
    @patch("genimg.ui.gradio_app.process_reference_image")
    @patch("genimg.ui.gradio_app.validate_prompt")
    @patch("genimg.ui.gradio_app.Config")
    def test_optimize_only_fills_result(
        self,
        mock_config_cls: MagicMock,
        _mock_validate: MagicMock,
        _mock_ref: MagicMock,
        mock_optimize: MagicMock,
    ) -> None:
        """Optimize-only stream yields status and optimized text."""
        config = MagicMock()
        config.openrouter_api_key = "sk-test"
        config.max_image_pixels = 2_000_000
        mock_config_cls.from_env.return_value = config
        config.validate.return_value = None
        mock_optimize.return_value = "optimized result"

        stream = gradio_app._run_optimize_only_stream("a cat", None)
        items = list(stream)
        mock_optimize.assert_called_once()
        assert len(items) >= 2
        assert items[-1][1] == "optimized result"
        assert "Optimized" in (items[-1][0] or "")
