"""
Integration tests for OpenRouter image generation.

Calls the real OpenRouter API (slow, costs money). Skips if OPENROUTER_API_KEY not set.
Run with: pytest --run-slow
"""

import os
from datetime import datetime
from pathlib import Path

import pytest

from genimg.core.config import Config
from genimg.core.image_gen import generate_image

# Project root (tests/integration -> tests -> project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_TMP_DIR = _PROJECT_ROOT / "tmp"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.expensive
class TestOpenRouterImageGeneration:
    """Real OpenRouter image generation (skips if OPENROUTER_API_KEY not set)."""

    @pytest.fixture(autouse=True)
    def _require_api_key(self) -> None:
        if not os.getenv("OPENROUTER_API_KEY", "").strip().startswith("sk-"):
            pytest.skip(
                "OPENROUTER_API_KEY not set or invalid (needs sk-...). "
                "Set in .env or environment to run this test."
            )

    def test_generate_image_returns_valid_result(self) -> None:
        """Call OpenRouter with a minimal prompt and assert result shape and sanity."""
        config = Config.from_env()
        prompt = "A single red circle on a white background."
        result = generate_image(prompt, config=config)

        assert result is not None
        assert len(result.image_data) > 0
        assert result.format in ("png", "jpeg", "jpg")
        assert result.model_used
        assert result.prompt_used == prompt
        assert result.generation_time >= 0
        assert result.had_reference is False

        # Always save output to tmp/ with a timestamped filename
        _TMP_DIR.mkdir(parents=True, exist_ok=True)
        ext = "jpg" if result.format in ("jpeg", "jpg") else result.format
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = _TMP_DIR / f"{stamp}.{ext}"
        out_path.write_bytes(result.image_data)
