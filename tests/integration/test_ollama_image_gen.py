"""
Integration tests for Ollama image generation.

Requires a local Ollama instance with an image model (e.g. x/z-image-turbo) pulled.
Run with: pytest --run-slow
"""

import pytest

from genimg.core.config import Config
from genimg.core.image_gen import GenerationResult, generate_image


@pytest.mark.integration
@pytest.mark.slow
class TestOllamaImageGeneration:
    """Ollama image generation (requires local Ollama with image model)."""

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
