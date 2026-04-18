"""Tests for character CLI default output path helper."""

from datetime import datetime

import pytest

from genimg.cli.utils import character_default_output_path, character_stem_from_title


@pytest.mark.unit
def test_character_default_output_path_pattern() -> None:
    fixed = datetime(2026, 4, 18, 14, 30, 22)
    p = character_default_output_path("My Hero", "png", now=fixed)
    assert p == "My-Hero-20260418_143022.png"


@pytest.mark.unit
def test_character_default_output_path_webp_extension() -> None:
    fixed = datetime(2026, 4, 18, 14, 30, 22)
    p = character_default_output_path("My Hero", "webp", now=fixed)
    assert p == "My-Hero-20260418_143022.webp"


@pytest.mark.unit
def test_character_stem_fallback_for_empty_title() -> None:
    stem, used = character_stem_from_title("   ///  ")
    assert stem == "character"
    assert used is True
