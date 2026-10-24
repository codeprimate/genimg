"""Unit tests for the output size pair and bitmap fit."""

import pytest
from PIL import Image

from genimg.core.output_size import (
    fit_image,
    ideal_pixel_size,
    normalize_size_pair,
    round_half_away_from_zero,
)
from genimg.utils.exceptions import ValidationError


@pytest.mark.unit
class TestNormalizeSizePair:
    def test_blank_and_none_pairs_are_omitted(self) -> None:
        assert normalize_size_pair(None, None) is None
        assert normalize_size_pair("", None) is None
        assert normalize_size_pair("  ", "") is None
        assert normalize_size_pair(None, "") is None

    def test_partial_pair_sets_field(self) -> None:
        with pytest.raises(ValidationError) as aspect_only:
            normalize_size_pair("16:9", None)
        assert aspect_only.value.field == "max_extent"

        with pytest.raises(ValidationError) as extent_only:
            normalize_size_pair(None, 2048)
        assert extent_only.value.field == "aspect_ratio"

        with pytest.raises(ValidationError) as blank_extent:
            normalize_size_pair("16:9", "  ")
        assert blank_extent.value.field == "max_extent"

    def test_extent_bounds(self) -> None:
        for bad in (1023, 2049, 1023.0, "2049"):
            with pytest.raises(ValidationError) as exc_info:
                normalize_size_pair("1:1", bad)
            assert exc_info.value.field == "max_extent"

        assert normalize_size_pair("1:1", 1024) == ("1:1", 1024)
        assert normalize_size_pair("1:1", 2048) == ("1:1", 2048)
        assert normalize_size_pair("1:1", 1024.0) == ("1:1", 1024)
        assert normalize_size_pair("1:1", "2048") == ("1:1", 2048)

    def test_aspect_tokens(self) -> None:
        for bad in ("wide", "16 : 9", "0:1", "1:0", "16-9"):
            with pytest.raises(ValidationError) as exc_info:
                normalize_size_pair(bad, 1024)
            assert exc_info.value.field == "aspect_ratio"

        assert normalize_size_pair("7:5", 1024) == ("7:5", 1024)
        assert normalize_size_pair("AUTO", 2048) == ("auto", 2048)
        assert normalize_size_pair(" Auto ", 1024) == ("auto", 1024)


@pytest.mark.unit
class TestIdealPixelSize:
    def test_named_examples(self) -> None:
        assert ideal_pixel_size("16:9", 1024) == (1024, 576)
        assert ideal_pixel_size("9:16", 1024) == (576, 1024)
        assert ideal_pixel_size("1:1", 2048) == (2048, 2048)
        assert ideal_pixel_size("auto", 2048) == (2048, 2048)

    def test_half_pixel_tie_rounds_away_from_zero(self) -> None:
        assert round_half_away_from_zero(1.5) == 2
        assert round_half_away_from_zero(2.5) == 3


@pytest.mark.unit
class TestFitImage:
    def test_auto_scales_without_crop(self) -> None:
        image = Image.new("RGB", (1000, 500), color=(1, 2, 3))
        fitted = fit_image(image, "auto", 1024)
        assert fitted.size == (1024, 512)
        assert fitted.mode == "RGB"

    def test_sixteen_nine_on_square_center_crops(self) -> None:
        image = Image.new("RGB", (800, 800), color=(4, 5, 6))
        fitted = fit_image(image, "16:9", 1024)
        assert fitted.size == (1024, 576)

    def test_sixteen_nine_on_wide_source_at_2048(self) -> None:
        image = Image.new("RGB", (2560, 1440), color=(7, 8, 9))
        fitted = fit_image(image, "16:9", 2048)
        assert fitted.size == (2048, 1152)

    def test_square_on_landscape_source(self) -> None:
        image = Image.new("RGB", (640, 480), color=(9, 8, 7))
        fitted = fit_image(image, "1:1", 2048)
        assert fitted.size == (2048, 2048)

    def test_non_schema_ratio(self) -> None:
        image = Image.new("RGB", (900, 700), color=(3, 3, 3))
        fitted = fit_image(image, "7:5", 1024)
        assert fitted.size == ideal_pixel_size("7:5", 1024)
        assert max(fitted.size) == 1024

    def test_source_already_target_size_is_unchanged(self) -> None:
        target = ideal_pixel_size("16:9", 1024)
        image = Image.new("L", target, color=40)
        fitted = fit_image(image, "16:9", 1024)
        assert fitted.size == target
        assert fitted.mode == "L"

    def test_auto_already_at_extent_returns_copy(self) -> None:
        image = Image.new("RGB", (1024, 400), color=(1, 1, 1))
        fitted = fit_image(image, "auto", 1024)
        assert fitted.size == (1024, 400)
        assert fitted is not image
