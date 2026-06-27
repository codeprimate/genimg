"""
Integration tests for Wiro image generation.

Calls the real Wiro API (slow, costs money). Skips if WIRO_API_KEY not set.
Run with: GENIMG_RUN_INTEGRATION_TESTS=1 pytest -m integration --run-slow
"""

import os
from pathlib import Path

import pytest

from genimg.core.config import Config
from genimg.core.image_gen import generate_image
from genimg.core.providers.wiro_client import WiroClient
from genimg.core.providers.wiro_schema import model_has_file_inputs, parse_model_slugs
from genimg.core.reference import process_reference_image

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_TMP_DIR = _PROJECT_ROOT / "tmp"
_FIXTURE_REF = Path(__file__).resolve().parent.parent / "fixtures" / "wiro_cat_keyboard_reference.png"
_SMOKE_OUTPUT = _TMP_DIR / "wiro_smoke_latest.png"
_DOG_EDIT_OUTPUT = _TMP_DIR / "wiro_dog_edit_latest.png"

_REF_EDIT_PROMPT = (
    "Same scene with a golden retriever dog playing the white electronic keyboard "
    "instead of the cat, photorealistic, preserve the keyboard and composition"
)


def _resolve_reference_test_model(config: Config) -> str:
    for env_name in (
        "GENIMG_WIRO_INTEGRATION_REFERENCE_MODEL",
        "GENIMG_WIRO_INTEGRATION_MODEL",
    ):
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return config.default_wiro_image_model


def _preflight_reference_model(config: Config, model: str) -> None:
    owner, project = parse_model_slugs(model)
    client = WiroClient(
        base_url=config.wiro_base_url,
        api_key=config.wiro_api_key,
        api_secret=config.wiro_api_secret or None,
        timeout=60,
    )
    schema = client.get_model_detail(owner, project)
    if not model_has_file_inputs(schema):
        pytest.fail(
            f"Model {model!r} has no file inputs. "
            "Set GENIMG_WIRO_INTEGRATION_REFERENCE_MODEL to a Wiro img2img/edit model "
            "that accepts an input image."
        )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.expensive
class TestWiroImageGeneration:
    """Real Wiro image generation (skips if WIRO_API_KEY not set)."""

    @pytest.fixture(autouse=True)
    def _require_api_key(self) -> None:
        if not os.getenv("WIRO_API_KEY", "").strip():
            pytest.skip(
                "WIRO_API_KEY not set. Set in .env or environment to run this test."
            )

    def test_wiro_text_to_image_smoke(self) -> None:
        config = Config.from_env()
        model = os.getenv("GENIMG_WIRO_INTEGRATION_MODEL", "").strip() or config.default_wiro_image_model
        prompt = "A single red circle on a white background."
        result = generate_image(
            prompt,
            config=config,
            provider="wiro",
            model=model,
        )

        assert result is not None
        assert len(result.image_data) > 0
        assert result.format in ("png", "jpeg", "jpg", "webp")
        assert result.model_used == model
        assert result.prompt_used == prompt
        assert result.generation_time >= 0
        assert result.had_reference is False

        _TMP_DIR.mkdir(parents=True, exist_ok=True)
        _SMOKE_OUTPUT.write_bytes(result.image_data)

    def test_wiro_reference_image_edit(self) -> None:
        if not _FIXTURE_REF.is_file():
            pytest.fail(f"Missing reference fixture: {_FIXTURE_REF}")

        config = Config.from_env()
        model = _resolve_reference_test_model(config)
        _preflight_reference_model(config, model)

        ref_b64, _ref_hash = process_reference_image(str(_FIXTURE_REF), config=config)
        result = generate_image(
            _REF_EDIT_PROMPT,
            config=config,
            provider="wiro",
            model=model,
            reference_images_b64=[ref_b64],
        )

        assert result is not None
        assert len(result.image_data) > 0
        assert result.had_reference is True
        assert result.prompt_used == _REF_EDIT_PROMPT

        _TMP_DIR.mkdir(parents=True, exist_ok=True)
        _DOG_EDIT_OUTPUT.write_bytes(result.image_data)
