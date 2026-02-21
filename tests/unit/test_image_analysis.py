"""Unit tests for image_analysis package (Phase 1–2: deps, layout, normalization, describe API)."""

import io

import pytest
from PIL import Image

from genimg.core.image_analysis import (
    describe_image,
    get_description,
    unload_describe_models,
)
from genimg.core.image_analysis.backends.florence import CAPTION_TASK_PROMPTS
from genimg.core.image_analysis.image_utils import normalize_image_to_rgb_pil
from genimg.utils.exceptions import ValidationError


def _minimal_png_bytes() -> bytes:
    """Minimal 1x1 PNG as bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", (1, 1), color=(128, 128, 128))
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def _minimal_jpeg_bytes() -> bytes:
    """Minimal 1x1 JPEG as bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", (1, 1), color=(0, 0, 0))
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()


@pytest.mark.unit
class TestImageAnalysisImports:
    """Package and public API importable."""

    def test_import_describe_image_and_unload(self):
        from genimg.core.image_analysis import describe_image, unload_describe_models

        assert callable(describe_image)
        assert callable(unload_describe_models)

    def test_unload_describe_models_idempotent(self):
        unload_describe_models()
        unload_describe_models()
        # No error; idempotent

    def test_describe_image_prose_returns_string(self, mocker):
        """describe_image(method='prose') returns caption from Florence backend."""
        mock_florence = mocker.MagicMock()
        mock_florence.caption.return_value = "A test caption."
        mocker.patch("genimg.core.image_analysis.api._get_florence", return_value=mock_florence)
        img = Image.new("RGB", (1, 1))
        out = describe_image(img, method="prose", verbosity="detailed")
        assert out == "A test caption."
        mock_florence.caption.assert_called_once()
        call_args = mock_florence.caption.call_args[0]
        assert call_args[1] == CAPTION_TASK_PROMPTS["detailed"]

    def test_describe_image_unknown_method_raises(self):
        img = Image.new("RGB", (1, 1))
        with pytest.raises(ValueError, match="Unknown method"):
            describe_image(img, method="invalid")


@pytest.mark.unit
class TestNormalizeImageToRgbPil:
    """normalize_image_to_rgb_pil: path, bytes, PIL -> RGB PIL."""

    def test_pil_rgb_returns_same_mode(self):
        img = Image.new("RGB", (2, 2), color=(1, 2, 3))
        out = normalize_image_to_rgb_pil(img)
        assert out.mode == "RGB"
        assert out.getpixel((0, 0)) == (1, 2, 3)

    def test_pil_rgba_converts_to_rgb(self):
        img = Image.new("RGBA", (2, 2), color=(1, 2, 3, 128))
        out = normalize_image_to_rgb_pil(img)
        assert out.mode == "RGB"
        # RGBA->RGB conversion; pixel present
        assert out.size == (2, 2)

    def test_bytes_png_success(self):
        png = _minimal_png_bytes()
        out = normalize_image_to_rgb_pil(png, format_hint="PNG")
        assert out.mode == "RGB"
        assert out.size == (1, 1)

    def test_bytes_jpeg_success(self):
        jpeg = _minimal_jpeg_bytes()
        out = normalize_image_to_rgb_pil(jpeg, format_hint="JPEG")
        assert out.mode == "RGB"
        assert out.size == (1, 1)

    def test_bytes_empty_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            normalize_image_to_rgb_pil(b"", format_hint="PNG")
        assert "empty" in str(exc_info.value).lower()

    def test_bytes_unknown_format_no_hint_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            normalize_image_to_rgb_pil(b"xxxxxxxxxxxx", format_hint=None)
        assert "format" in str(exc_info.value).lower()

    def test_path_valid_png(self, tmp_path):
        png_path = tmp_path / "x.png"
        png_path.write_bytes(_minimal_png_bytes())
        out = normalize_image_to_rgb_pil(str(png_path))
        assert out.mode == "RGB"
        assert out.size == (1, 1)

    def test_path_valid_png_path_object(self, tmp_path):
        png_path = tmp_path / "y.png"
        png_path.write_bytes(_minimal_png_bytes())
        out = normalize_image_to_rgb_pil(png_path)
        assert out.mode == "RGB"

    def test_path_unsupported_format_raises(self, tmp_path):
        bad = tmp_path / "x.xyz"
        bad.write_bytes(b"not an image")
        with pytest.raises(ValidationError) as exc_info:
            normalize_image_to_rgb_pil(str(bad))
        assert "Unsupported" in str(exc_info.value) or "format" in str(exc_info.value).lower()

    def test_path_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            normalize_image_to_rgb_pil("/nonexistent/image.png")


@pytest.mark.unit
class TestDescribeImageWithMocks:
    """describe_image and get_description with mocked backends."""

    def test_describe_image_tags_returns_comma_separated(self, mocker):
        mock_joytag = mocker.MagicMock()
        mock_joytag.predict_tags.return_value = [("tag1", 0.9), ("tag2", 0.5)]
        mocker.patch("genimg.core.image_analysis.api._get_joytag", return_value=mock_joytag)
        img = Image.new("RGB", (1, 1))
        out = describe_image(img, method="tags", tag_threshold=0.4)
        assert out == "tag1, tag2"
        mock_joytag.predict_tags.assert_called_once_with(mocker.ANY, 0.4)

    def test_get_description_cache_miss_then_hit(self, mocker):
        mock_florence = mocker.MagicMock()
        mock_florence.caption.return_value = "Cached caption."
        mocker.patch("genimg.core.image_analysis.api._get_florence", return_value=mock_florence)
        img = Image.new("RGB", (1, 1))
        out1 = get_description(img, image_hash="abc123", method="prose", verbosity="brief")
        assert out1 == "Cached caption."
        assert mock_florence.caption.call_count == 1
        out2 = get_description(img, image_hash="abc123", method="prose", verbosity="brief")
        assert out2 == "Cached caption."
        assert mock_florence.caption.call_count == 1

    def test_get_description_different_options_cache_miss(self, mocker):
        mock_florence = mocker.MagicMock()
        mock_florence.caption.return_value = "Caption."
        mocker.patch("genimg.core.image_analysis.api._get_florence", return_value=mock_florence)
        img = Image.new("RGB", (1, 1))
        get_description(img, image_hash="h1", method="prose", verbosity="brief")
        get_description(img, image_hash="h1", method="prose", verbosity="detailed")
        assert mock_florence.caption.call_count == 2

    def test_describe_after_unload_works(self, mocker):
        """After unload_describe_models(), describe_image still works (backend re-created)."""
        unload_describe_models()
        mock_florence = mocker.MagicMock()
        mock_florence.caption.return_value = "After unload."
        mocker.patch("genimg.core.image_analysis.api._get_florence", return_value=mock_florence)
        img = Image.new("RGB", (1, 1))
        out = describe_image(img, method="prose", verbosity="brief")
        assert out == "After unload."
        mock_florence.caption.assert_called_once()
