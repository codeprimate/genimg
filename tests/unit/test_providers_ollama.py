"""Unit tests for the Ollama image generation provider."""

import base64
import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from genimg.core.config import Config
from genimg.core.providers.ollama import OllamaProvider
from genimg.utils.exceptions import APIError, ValidationError

# Minimal valid image bytes for PIL
_MINIMAL_PNG_BUF = io.BytesIO()
Image.new("RGB", (1, 1), color=(0, 0, 0)).save(_MINIMAL_PNG_BUF, format="PNG")
MINIMAL_PNG = _MINIMAL_PNG_BUF.getvalue()


@pytest.mark.unit
class TestOllamaProvider:
    def test_supports_reference_image_false(self):
        assert OllamaProvider.supports_reference_image is False

    def test_validate_config_accepts_empty_when_default_available(self):
        """Empty ollama_base_url falls back to DEFAULT_OLLAMA_BASE_URL; no raise."""
        provider = OllamaProvider()
        config = Config(ollama_base_url="", default_image_provider="ollama")
        provider._validate_config(config)

    def test_validate_config_raises_when_no_base_url_and_no_default(self):
        """When ollama_base_url is empty and default is patched empty, ValidationError."""
        provider = OllamaProvider()
        config = Config(ollama_base_url="", default_image_provider="ollama")
        with patch(
            "genimg.core.providers.ollama.DEFAULT_OLLAMA_BASE_URL",
            "",
        ):
            with pytest.raises(ValidationError) as exc_info:
                provider._validate_config(config)
        assert exc_info.value.field == "ollama_base_url"

    def test_generate_success_json_with_image_key(self):
        config = Config(
            ollama_base_url="http://127.0.0.1:11434",
            default_image_provider="ollama",
        )
        b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "application/json"
        mock_response.json.return_value = {"image": b64}
        mock_response.text = ""
        provider = OllamaProvider()
        with patch("genimg.core.providers.ollama.requests.post", return_value=mock_response):
            result = provider.generate(
                "a cat",
                model="x/z-image-turbo",
                reference_image_b64=None,
                timeout=60,
                config=config,
                cancel_check=None,
            )
        assert result.image is not None
        assert result.model_used == "x/z-image-turbo"
        assert result.prompt_used == "a cat"
        assert result.had_reference is False
        assert len(result.image_data) > 0

    def test_generate_success_json_with_response_key(self):
        """Some Ollama image models return base64 in 'response'."""
        config = Config(
            ollama_base_url="http://127.0.0.1:11434",
            default_image_provider="ollama",
        )
        b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "application/json"
        mock_response.json.return_value = {"response": b64}
        mock_response.text = ""
        provider = OllamaProvider()
        with patch("genimg.core.providers.ollama.requests.post", return_value=mock_response):
            result = provider.generate(
                "a dog",
                model="flux",
                reference_image_b64=None,
                timeout=60,
                config=config,
                cancel_check=None,
            )
        assert result.image is not None
        assert result.prompt_used == "a dog"

    def test_generate_success_binary_image_response(self):
        config = Config(
            ollama_base_url="http://127.0.0.1:11434",
            default_image_provider="ollama",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "image/png"
        mock_response.content = MINIMAL_PNG
        mock_response.text = ""
        provider = OllamaProvider()
        with patch("genimg.core.providers.ollama.requests.post", return_value=mock_response):
            result = provider.generate(
                "bird",
                model="x/flux2-klein",
                reference_image_b64=None,
                timeout=60,
                config=config,
                cancel_check=None,
            )
        assert result.image is not None
        assert result.format == "png"

    def test_generate_http_500_raises_api_error(self):
        config = Config(
            ollama_base_url="http://127.0.0.1:11434",
            default_image_provider="ollama",
        )
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        provider = OllamaProvider()
        with patch("genimg.core.providers.ollama.requests.post", return_value=mock_response):
            with pytest.raises(APIError) as exc_info:
                provider.generate(
                    "x",
                    model="flux",
                    reference_image_b64=None,
                    timeout=60,
                    config=config,
                    cancel_check=None,
                )
        assert exc_info.value.status_code == 500

    def test_generate_no_image_in_json_raises_api_error(self):
        config = Config(
            ollama_base_url="http://127.0.0.1:11434",
            default_image_provider="ollama",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers.get.return_value = "application/json"
        mock_response.json.return_value = {"done": True}
        mock_response.text = "{}"
        provider = OllamaProvider()
        with patch("genimg.core.providers.ollama.requests.post", return_value=mock_response):
            with pytest.raises(APIError) as exc_info:
                provider.generate(
                    "x",
                    model="flux",
                    reference_image_b64=None,
                    timeout=60,
                    config=config,
                    cancel_check=None,
                )
        assert "No image" in str(exc_info.value)
