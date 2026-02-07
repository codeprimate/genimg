"""Unit tests for image generation (result shape, validation, mocked API)."""

import base64
import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from genimg.core.config import Config
from genimg.core.image_gen import (
    GenerationResult,
    _format_from_content_type,
    generate_image,
)

# Minimal valid image bytes so Image.open() succeeds in the library
_MINIMAL_PNG_BUF = io.BytesIO()
Image.new("RGB", (1, 1), color=(0, 0, 0)).save(_MINIMAL_PNG_BUF, format="PNG")
MINIMAL_PNG = _MINIMAL_PNG_BUF.getvalue()

_MINIMAL_JPEG_BUF = io.BytesIO()
Image.new("RGB", (1, 1), color=(0, 0, 0)).save(_MINIMAL_JPEG_BUF, format="JPEG")
MINIMAL_JPEG = _MINIMAL_JPEG_BUF.getvalue()
from genimg.utils.exceptions import (
    APIError,
    CancellationError,
    NetworkError,
    RequestTimeoutError,
    ValidationError,
)


@pytest.mark.unit
class TestGenerationResult:
    def test_has_image_and_format(self):
        pil_image = Image.open(io.BytesIO(MINIMAL_PNG)).copy()
        r = GenerationResult(
            image=pil_image,
            _format="png",
            generation_time=1.0,
            model_used="m",
            prompt_used="p",
            had_reference=False,
        )
        assert r.format == "png"
        assert r.image is not None
        assert len(r.image_data) > 0
        assert r.image_data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_format_from_content_type(self):
        assert _format_from_content_type("image/jpeg") == "jpeg"
        assert _format_from_content_type("image/png") == "png"
        assert _format_from_content_type("image/PNG; charset=utf-8") == "png"
        assert _format_from_content_type("") == "png"
        assert _format_from_content_type("text/plain") == "png"


@pytest.mark.unit
class TestGenerateImageValidation:
    def test_empty_prompt_raises(self):
        config = Config(openrouter_api_key="sk-ok")
        with pytest.raises(ValidationError) as exc_info:
            generate_image("", config=config)
        assert exc_info.value.field == "prompt"

    def test_whitespace_prompt_raises(self):
        config = Config(openrouter_api_key="sk-ok")
        with pytest.raises(ValidationError):
            generate_image("   \n", config=config)

    def test_missing_api_key_raises(self):
        config = Config(openrouter_api_key="")
        with pytest.raises(ValidationError) as exc_info:
            generate_image("a cat", config=config)
        assert exc_info.value.field == "api_key"


@pytest.mark.unit
class TestGenerateImageMocked:
    """Tests for generate_image with mocked requests.post."""

    def test_success_binary_image_response(self):
        config = Config(openrouter_api_key="sk-ok")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "image/png"
        mock_response.content = MINIMAL_PNG
        mock_response.text = ""
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response):
            result = generate_image("a cat", config=config)
        assert result.image is not None
        assert result.format == "png"
        assert len(result.image_data) > 0
        assert result.image_data[:8] == b"\x89PNG\r\n\x1a\n"
        assert result.model_used == config.default_image_model
        assert result.prompt_used == "a cat"
        assert result.had_reference is False

    def test_success_json_response_with_data_url(self):
        config = Config(openrouter_api_key="sk-ok")
        b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "application/json"
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "images": [
                            {"image_url": {"url": f"data:image/png;base64,{b64}"}}
                        ]
                    }
                }
            ]
        }
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response):
            result = generate_image("a dog", config=config)
        assert result.image is not None
        assert result.format == "png"
        assert len(result.image_data) > 0
        assert result.prompt_used == "a dog"

    def test_success_json_response_raw_base64(self):
        config = Config(openrouter_api_key="sk-ok")
        b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "application/json"
        mock_response.json.return_value = {
            "choices": [{"message": {"images": [{"image_url": {"url": b64}}]}}]
        }
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response):
            result = generate_image("bird", config=config)
        assert result.image is not None
        assert result.format == "png"
        assert len(result.image_data) > 0

    def test_config_override_used(self):
        config = Config(
            openrouter_api_key="sk-ok",
            default_image_model="custom/model",
            openrouter_base_url="https://custom.example/v1",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "image/jpeg"
        mock_response.content = MINIMAL_JPEG
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response) as m:
            generate_image("x", config=config)
        call_kw = m.call_args[1]
        assert call_kw["json"]["model"] == "custom/model"
        assert "custom.example" in m.call_args[0][0]

    def test_reference_image_in_payload(self):
        config = Config(openrouter_api_key="sk-ok")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "image/png"
        mock_response.content = MINIMAL_PNG
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response) as m:
            generate_image("same but blue", reference_image_b64="YXNk", config=config)
        payload = m.call_args[1]["json"]
        content = payload["messages"][0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert any("image_url" in str(p) for p in content)

    def test_http_401_raises_api_error(self):
        config = Config(openrouter_api_key="sk-ok")
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response):
            with pytest.raises(APIError) as exc_info:
                generate_image("x", config=config)
        assert exc_info.value.status_code == 401

    def test_http_404_raises_api_error(self):
        config = Config(openrouter_api_key="sk-ok")
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response):
            with pytest.raises(APIError) as exc_info:
                generate_image("x", config=config)
        assert exc_info.value.status_code == 404

    def test_http_429_raises_api_error(self):
        config = Config(openrouter_api_key="sk-ok")
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit"
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response):
            with pytest.raises(APIError) as exc_info:
                generate_image("x", config=config)
        assert exc_info.value.status_code == 429

    def test_http_500_raises_api_error(self):
        config = Config(openrouter_api_key="sk-ok")
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.text = "Bad gateway"
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response):
            with pytest.raises(APIError) as exc_info:
                generate_image("x", config=config)
        assert exc_info.value.status_code == 502

    def test_http_non_200_raises_api_error(self):
        config = Config(openrouter_api_key="sk-ok")
        mock_response = MagicMock()
        mock_response.status_code = 418
        mock_response.text = "teapot"
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response):
            with pytest.raises(APIError) as exc_info:
                generate_image("x", config=config)
        assert exc_info.value.status_code == 418

    def test_json_parse_error_raises_api_error(self):
        config = Config(openrouter_api_key="sk-ok")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "application/json"
        mock_response.json.side_effect = ValueError("bad json")
        mock_response.text = "{invalid"
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response):
            with pytest.raises(APIError):
                generate_image("x", config=config)

    def test_no_images_in_response_raises_api_error(self):
        config = Config(openrouter_api_key="sk-ok")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "application/json"
        mock_response.json.return_value = {"choices": [{"message": {"images": []}}]}
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response):
            with pytest.raises(APIError) as exc_info:
                generate_image("x", config=config)
        assert "No images" in str(exc_info.value)

    def test_no_image_url_in_response_raises_api_error(self):
        config = Config(openrouter_api_key="sk-ok")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "application/json"
        mock_response.json.return_value = {
            "choices": [{"message": {"images": [{"image_url": {}}]}}]
        }
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response):
            with pytest.raises(APIError):
                generate_image("x", config=config)

    def test_malformed_json_response_raises_api_error(self):
        """KeyError/IndexError when extracting image from response raises APIError."""
        config = Config(openrouter_api_key="sk-ok")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "application/json"
        mock_response.json.return_value = {"choices": []}  # no [0] -> IndexError
        with patch("genimg.core.image_gen.requests.post", return_value=mock_response):
            with pytest.raises(APIError) as exc_info:
                generate_image("x", config=config)
        assert "extract" in str(exc_info.value).lower() or "response" in str(exc_info.value).lower()

    def test_timeout_raises_request_timeout_error(self):
        import requests

        config = Config(openrouter_api_key="sk-ok")
        with patch("genimg.core.image_gen.requests.post") as m:
            m.side_effect = requests.exceptions.Timeout()
            with pytest.raises(RequestTimeoutError):
                generate_image("x", config=config, timeout=30)

    def test_connection_error_raises_network_error(self):
        import requests

        config = Config(openrouter_api_key="sk-ok")
        with patch("genimg.core.image_gen.requests.post") as m:
            m.side_effect = requests.exceptions.ConnectionError("refused")
            with pytest.raises(NetworkError):
                generate_image("x", config=config)

    def test_request_exception_raises_network_error(self):
        import requests

        config = Config(openrouter_api_key="sk-ok")
        with patch("genimg.core.image_gen.requests.post") as m:
            m.side_effect = requests.exceptions.RequestException("other")
            with pytest.raises(NetworkError):
                generate_image("x", config=config)

    def test_cancel_check_raises_cancellation_error(self):
        """When cancel_check returns True during request, CancellationError is raised."""
        import time

        config = Config(openrouter_api_key="sk-ok")
        call_count = [0]

        def slow_then_cancel():
            call_count[0] += 1
            if call_count[0] == 1:
                time.sleep(0.1)
            return call_count[0] >= 2

        def blocking_post(*args, **kwargs):
            time.sleep(10)
            raise AssertionError("Should have been cancelled")

        with patch("genimg.core.image_gen.requests.post", side_effect=blocking_post):
            with pytest.raises(CancellationError) as exc_info:
                generate_image("x", config=config, cancel_check=slow_then_cancel)
        assert "cancelled" in str(exc_info.value).lower()
