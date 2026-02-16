"""
Optional integration tests for Ollama image generation.

These tests call a local Ollama instance. They are skipped unless opted in.
Run when Ollama is running with an image model (e.g. x/z-image-turbo) pulled.

To run:
  GENIMG_OLLAMA_IMAGE_TEST=1 pytest tests/integration/test_ollama_image_gen.py -m integration
  # or with custom base URL:
  GENIMG_OLLAMA_IMAGE_TEST=1 OLLAMA_BASE_URL=http://localhost:11434 pytest ...
"""

import os

import pytest

from genimg.core.config import Config
from genimg.core.image_gen import GenerationResult, generate_image


def _ollama_image_test_enabled() -> bool:
    return os.getenv("GENIMG_OLLAMA_IMAGE_TEST", "").strip() == "1"


@pytest.mark.integration
class TestOllamaImageGeneration:
    """Ollama image generation (requires local Ollama + opt-in env)."""

    @pytest.fixture(autouse=True)
    def _require_opt_in(self) -> None:
        if not _ollama_image_test_enabled():
            pytest.skip(
                "Ollama image integration tests are disabled. "
                "Set GENIMG_OLLAMA_IMAGE_TEST=1 to run (requires Ollama with an image model)."
            )

    def test_generate_image_returns_valid_result(self) -> None:
        """Call Ollama with provider=ollama and assert result shape and sanity."""
        config = Config.from_env()
        config.default_image_provider = "ollama"
        # Use default ollama_base_url from config (e.g. http://127.0.0.1:11434)
        prompt = "A single red circle on a white background."
        result = generate_image(
            prompt,
            config=config,
            provider="ollama",
            model="x/z-image-turbo",
        )

        assert isinstance(result, GenerationResult)
        assert result.image is not None
        assert len(result.image_data) > 0
        assert result.format in ("png", "jpeg", "jpg")
        assert result.model_used == "x/z-image-turbo"
        assert result.prompt_used == prompt
        assert result.generation_time >= 0
        assert result.had_reference is False
