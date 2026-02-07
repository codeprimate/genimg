"""
Integration tests for OpenRouter image generation.

These tests call the real OpenRouter API. They are slow and cost money.
Run rarely and only when you need to verify the live API path.

To run:
  GENIMG_RUN_INTEGRATION_TESTS=1 OPENROUTER_API_KEY=sk-... pytest -m integration
  # or
  GENIMG_RUN_INTEGRATION_TESTS=1 make test-integration
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


def _integration_enabled() -> bool:
    return os.getenv("GENIMG_RUN_INTEGRATION_TESTS", "").strip() == "1"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.expensive
class TestOpenRouterImageGeneration:
    """Real OpenRouter image generation (requires API key and opt-in env)."""

    @pytest.fixture(autouse=True)
    def _require_opt_in(self) -> None:
        if not _integration_enabled():
            pytest.skip(
                "Integration tests are disabled. "
                "Set GENIMG_RUN_INTEGRATION_TESTS=1 to run (slow, costs money)."
            )
        if not os.getenv("OPENROUTER_API_KEY", "").strip().startswith("sk-"):
            pytest.skip(
                "OPENROUTER_API_KEY not set or invalid. "
                "Set it in .env or environment to run integration tests."
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
