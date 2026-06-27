"""Unit tests for WiroProvider."""

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from genimg.core.config import Config
from genimg.core.providers.wiro import WiroProvider
from genimg.core.providers.wiro_client import WiroRunResult, WiroTask
from genimg.utils.exceptions import APIError, CancellationError, ValidationError

_MINIMAL_PNG_BUF = io.BytesIO()
Image.new("RGB", (1, 1), color=(0, 0, 0)).save(_MINIMAL_PNG_BUF, format="PNG")
MINIMAL_PNG = _MINIMAL_PNG_BUF.getvalue()

SCHEMA = {
    "tool": [
        {
            "parameters": [
                {"items": [{"id": "prompt", "type": "textarea", "required": True}]}
            ]
        }
    ]
}


@pytest.mark.unit
class TestWiroProvider:
    def test_supports_reference_image_true(self):
        assert WiroProvider.supports_reference_image is True

    def test_missing_api_key_raises(self):
        provider = WiroProvider()
        config = Config(wiro_api_key="", default_wiro_image_model="owner/model")
        with pytest.raises(ValidationError) as exc_info:
            provider.generate(
                "prompt",
                "owner/model",
                None,
                60,
                config,
                None,
            )
        assert exc_info.value.field == "api_key"

    @patch.object(WiroProvider, "_cached_schema", return_value=SCHEMA)
    def test_successful_generation(self, _mock_schema):
        provider = WiroProvider()
        config = Config(wiro_api_key="key", default_wiro_image_model="owner/model")
        mock_client = MagicMock()
        mock_client.run_model.return_value = WiroRunResult(
            taskid="1",
            socketaccesstoken="tok",
        )
        mock_client.get_task.return_value = WiroTask(
            taskid="1",
            socketaccesstoken="tok",
            status="task_postprocess_end",
            pexit="0",
            outputs=(
                {"url": "https://cdn.example/out.png", "contenttype": "image/png"},
            ),
        )
        mock_client.download_url.return_value = MINIMAL_PNG

        with patch.object(WiroProvider, "_client", return_value=mock_client):
            result = provider.generate(
                "a cat",
                "owner/model",
                None,
                120,
                config,
                None,
            )

        assert result.prompt_used == "a cat"
        assert result.model_used == "owner/model"
        assert result.had_reference is False
        assert isinstance(result.image, Image.Image)
        mock_client.run_model.assert_called_once()

    @patch.object(WiroProvider, "_cached_schema", return_value=SCHEMA)
    def test_pexit_failure_raises_api_error(self, _mock_schema):
        provider = WiroProvider()
        config = Config(wiro_api_key="key")
        mock_client = MagicMock()
        mock_client.run_model.return_value = WiroRunResult(taskid="1", socketaccesstoken="tok")
        mock_client.get_task.return_value = WiroTask(
            taskid="1",
            socketaccesstoken="tok",
            status="task_postprocess_end",
            pexit="1",
            outputs=(),
        )

        with patch.object(WiroProvider, "_client", return_value=mock_client):
            with pytest.raises(APIError):
                provider.generate("x", "owner/model", None, 120, config, None)

    @patch.object(WiroProvider, "_cached_schema", return_value=SCHEMA)
    def test_cancel_during_poll_calls_kill(self, _mock_schema):
        provider = WiroProvider()
        config = Config(wiro_api_key="key")
        mock_client = MagicMock()
        mock_client.run_model.return_value = WiroRunResult(taskid="1", socketaccesstoken="tok")
        mock_client.get_task.return_value = WiroTask(
            taskid="1",
            socketaccesstoken="tok",
            status="task_start",
            pexit="",
            outputs=(),
        )

        cancelled = False

        def cancel_check() -> bool:
            nonlocal cancelled
            if not cancelled:
                cancelled = True
            return cancelled

        with patch.object(WiroProvider, "_client", return_value=mock_client):
            with pytest.raises(CancellationError):
                provider.generate(
                    "x",
                    "owner/model",
                    None,
                    120,
                    config,
                    cancel_check,
                )
        mock_client.kill_task.assert_called_with("tok")
