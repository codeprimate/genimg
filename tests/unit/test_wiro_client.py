"""Unit tests for Wiro HTTP client response parsing."""

from unittest.mock import MagicMock, patch

import pytest

from genimg.core.providers.wiro_client import WiroClient
from genimg.utils.exceptions import APIError


@pytest.mark.unit
class TestWiroClientRun:
    def test_run_parses_top_level_tokens(self):
        client = WiroClient(base_url="https://api.wiro.ai/v1", api_key="key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": True,
            "errors": [],
            "taskid": "534574",
            "socketaccesstoken": "token-abc",
        }
        with patch("genimg.core.providers.wiro_client.requests.post", return_value=mock_response):
            from genimg.core.providers.wiro_schema import build_run_plan

            plan = build_run_plan(
                {"tool": [{"parameters": [{"items": [{"id": "prompt", "type": "textarea"}]}]}]},
                prompt="hi",
                reference_images_b64=None,
            )
            result = client.run_model("owner", "model", plan)
        assert result.taskid == "534574"
        assert result.socketaccesstoken == "token-abc"

    def test_run_envelope_error_raises_api_error(self):
        client = WiroClient(base_url="https://api.wiro.ai/v1", api_key="key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": False,
            "errors": ["bad params"],
        }
        with patch("genimg.core.providers.wiro_client.requests.post", return_value=mock_response):
            from genimg.core.providers.wiro_schema import build_run_plan

            plan = build_run_plan(
                {"tool": [{"parameters": [{"items": [{"id": "prompt", "type": "textarea"}]}]}]},
                prompt="hi",
                reference_images_b64=None,
            )
            with pytest.raises(APIError) as exc_info:
                client.run_model("owner", "model", plan)
            assert "bad params" in str(exc_info.value)


@pytest.mark.unit
class TestWiroClientTaskDetail:
    def test_get_task_parses_tasklist(self):
        client = WiroClient(base_url="https://api.wiro.ai/v1", api_key="key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": True,
            "errors": [],
            "tasklist": [
                {
                    "id": "1",
                    "socketaccesstoken": "tok",
                    "status": "task_postprocess_end",
                    "pexit": "0",
                    "outputs": [
                        {
                            "url": "https://cdn.example/out.png",
                            "contenttype": "image/png",
                        }
                    ],
                }
            ],
        }
        with patch("genimg.core.providers.wiro_client.requests.request", return_value=mock_response):
            task = client.get_task(tasktoken="tok")
        assert task is not None
        assert task.status == "task_postprocess_end"
        assert task.pexit == "0"
        assert task.outputs[0]["url"] == "https://cdn.example/out.png"
