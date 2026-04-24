"""Unit tests for canonical provider id constants."""

import subprocess
import sys

import pytest

from genimg.core import provider_ids


@pytest.mark.unit
def test_known_image_provider_ids_contains_expected_values() -> None:
    assert provider_ids.PROVIDER_OPENROUTER in provider_ids.KNOWN_IMAGE_PROVIDER_IDS
    assert provider_ids.PROVIDER_OLLAMA in provider_ids.KNOWN_IMAGE_PROVIDER_IDS
    assert provider_ids.PROVIDER_DRAW_THINGS in provider_ids.KNOWN_IMAGE_PROVIDER_IDS


@pytest.mark.unit
def test_draw_things_appears_exactly_once() -> None:
    assert provider_ids.KNOWN_IMAGE_PROVIDER_IDS.count(provider_ids.PROVIDER_DRAW_THINGS) == 1


@pytest.mark.unit
def test_import_is_lightweight_without_grpc_modules_loaded() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import genimg.core.provider_ids; "
                "print(int('grpc' in sys.modules or 'grpcio' in sys.modules))"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout.strip() == "0"
