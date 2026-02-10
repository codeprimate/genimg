"""Unit tests for reference image helpers and process_reference_image."""

import base64
import io

import pytest
from PIL import Image

from genimg.core.config import Config
from genimg.core.reference import (
    SUPPORTED_FORMATS,
    _infer_format_from_magic,
    _load_image_source,
    _normalize_format,
    create_image_data_url,
    encode_image_base64,
    get_image_hash,
    load_image,
    process_reference_image,
    resize_image,
    validate_image_format,
)
from genimg.utils.exceptions import ValidationError

# PNG magic
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# JPEG magic
JPEG_MAGIC = b"\xff\xd8\xff"
# WebP: RIFF....WEBP
WEBP_MAGIC = b"RIFF\x00\x00\x00\x00WEBP"


def _minimal_png_bytes() -> bytes:
    """Minimal 1x1 PNG as bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", (1, 1), color=(128, 128, 128))
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def _minimal_jpeg_bytes() -> bytes:
    """Minimal 1x1 JPEG as bytes (has JPEG magic)."""
    buf = io.BytesIO()
    img = Image.new("RGB", (1, 1), color=(0, 0, 0))
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()


@pytest.mark.unit
class TestNormalizeFormat:
    def test_jpg_to_jpeg(self):
        assert _normalize_format("JPG") == "JPEG"
        assert _normalize_format("jpg") == "JPEG"

    def test_mime_type_stripped(self):
        assert _normalize_format("image/jpeg") == "JPEG"
        assert _normalize_format("image/PNG") == "PNG"

    def test_unsupported_returns_none(self):
        assert _normalize_format("image/xyz") is None

    def test_none_returns_none(self):
        assert _normalize_format(None) is None


@pytest.mark.unit
class TestInferFormatFromMagic:
    def test_png(self):
        data = PNG_MAGIC + b"\x00" * 20
        assert _infer_format_from_magic(data) == "PNG"

    def test_jpeg(self):
        data = JPEG_MAGIC + b"\x00" * 20
        assert _infer_format_from_magic(data) == "JPEG"

    def test_webp(self):
        data = WEBP_MAGIC + b"\x00" * 20
        assert _infer_format_from_magic(data) == "WEBP"

    def test_short_data_returns_none(self):
        assert _infer_format_from_magic(b"\x89") is None
        assert _infer_format_from_magic(b"") is None

    def test_unknown_returns_none(self):
        assert _infer_format_from_magic(b"xxxxyyyyzzzz") is None


@pytest.mark.unit
class TestSupportedFormats:
    def test_includes_expected(self):
        assert "PNG" in SUPPORTED_FORMATS
        assert "JPEG" in SUPPORTED_FORMATS
        assert "WEBP" in SUPPORTED_FORMATS


@pytest.mark.unit
class TestLoadImageSource:
    def test_bytes_empty_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            _load_image_source(b"", format_hint="PNG")
        assert "empty" in str(exc_info.value).lower()

    def test_bytes_with_format_hint_success(self):
        png = _minimal_png_bytes()
        image, fmt = _load_image_source(png, format_hint="PNG")
        assert image.size == (1, 1)
        assert fmt == "PNG"

    def test_bytes_with_mime_hint(self):
        png = _minimal_png_bytes()
        image, fmt = _load_image_source(png, format_hint="image/png")
        assert fmt == "PNG"

    def test_bytes_no_hint_infers_from_magic(self):
        png = _minimal_png_bytes()
        image, fmt = _load_image_source(png, format_hint=None)
        assert fmt == "PNG"
        jpeg = _minimal_jpeg_bytes()
        image2, fmt2 = _load_image_source(jpeg, format_hint=None)
        assert fmt2 == "JPEG"

    def test_bytes_unknown_format_no_hint_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            _load_image_source(b"xxxxxxxxxxxx", format_hint=None)
        assert "format" in str(exc_info.value).lower()

    def test_path_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            _load_image_source("/nonexistent/path.png")

    def test_path_unsupported_suffix_raises(self, tmp_path):
        bad = tmp_path / "x.xyz"
        bad.write_bytes(b"not an image")
        with pytest.raises(ValidationError) as exc_info:
            _load_image_source(str(bad))
        assert "Unsupported" in str(exc_info.value) or "format" in str(exc_info.value).lower()


@pytest.mark.unit
class TestCreateImageDataUrl:
    def test_returns_data_url(self):
        url = create_image_data_url("YWJj", mime_type="image/jpeg")
        assert url.startswith("data:image/jpeg;base64,")
        assert "YWJj" in url

    def test_default_mime(self):
        url = create_image_data_url("ZGVm")
        assert "image/jpeg" in url


@pytest.mark.unit
class TestResizeImage:
    def test_small_image_unchanged(self):
        img = Image.new("RGB", (10, 10))
        out = resize_image(img, max_pixels=1_000_000, min_pixels=1)
        assert out.size == (10, 10)

    def test_large_image_resized(self):
        img = Image.new("RGB", (2000, 2000))  # 4M pixels
        out = resize_image(img, max_pixels=100, min_pixels=1)
        assert out.size != (2000, 2000)
        assert out.size[0] * out.size[1] <= 100

    def test_raises_when_below_min_pixels(self):
        img = Image.new("RGB", (10, 10))  # 100 pixels
        with pytest.raises(ValidationError) as exc_info:
            resize_image(img, max_pixels=1_000_000, min_pixels=2500)
        assert "too small" in str(exc_info.value)
        assert "2500" in str(exc_info.value)
        assert exc_info.value.field == "image"

    def test_aspect_ratio_pad_top_bottom(self):
        # 20x10 (wide) with aspect 1:1 -> padded to 20x20 (top/bottom white)
        img = Image.new("RGB", (20, 10), color=(100, 100, 100))
        out = resize_image(
            img, max_pixels=1_000_000, min_pixels=1, aspect_ratio=(1, 1)
        )
        assert out.size == (20, 20)
        # Center of pasted image (original 20x10 at paste_y=5)
        assert out.getpixel((10, 10)) == (100, 100, 100)
        # Top/bottom padding should be white
        assert out.getpixel((10, 0)) == (255, 255, 255)
        assert out.getpixel((10, 19)) == (255, 255, 255)

    def test_aspect_ratio_pad_left_right(self):
        # 10x20 (tall) with aspect 1:1 -> padded to 20x20 (left/right white)
        img = Image.new("RGB", (10, 20), color=(100, 100, 100))
        out = resize_image(
            img, max_pixels=1_000_000, min_pixels=1, aspect_ratio=(1, 1)
        )
        assert out.size == (20, 20)
        assert out.getpixel((5, 10)) == (100, 100, 100)
        assert out.getpixel((0, 10)) == (255, 255, 255)
        assert out.getpixel((19, 10)) == (255, 255, 255)

    def test_aspect_ratio_no_pad_when_already_matches(self):
        img = Image.new("RGB", (10, 10))
        out = resize_image(
            img, max_pixels=1_000_000, min_pixels=1, aspect_ratio=(1, 1)
        )
        assert out.size == (10, 10)


@pytest.mark.unit
class TestConvertToRgb:
    def test_rgb_unchanged(self):
        from genimg.core.reference import convert_to_rgb

        img = Image.new("RGB", (1, 1))
        out = convert_to_rgb(img)
        assert out.mode == "RGB"

    def test_rgba_converted(self):
        from genimg.core.reference import convert_to_rgb

        img = Image.new("RGBA", (1, 1), (255, 0, 0, 128))
        out = convert_to_rgb(img)
        assert out.mode == "RGB"


@pytest.mark.unit
class TestEncodeImageBase64:
    def test_returns_base64_string(self):
        img = Image.new("RGB", (1, 1))
        enc = encode_image_base64(img, format="PNG")
        assert isinstance(enc, str)
        assert len(enc) > 0


@pytest.mark.unit
class TestValidateImageFormat:
    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            validate_image_format("/nonexistent/file.png")

    def test_unsupported_extension_raises(self, tmp_path):
        f = tmp_path / "x.xyz"
        f.write_bytes(b"x")
        with pytest.raises(ValidationError) as exc_info:
            validate_image_format(str(f))
        assert "format" in str(exc_info.value).lower() or "Unsupported" in str(exc_info.value)


@pytest.mark.unit
class TestLoadImage:
    def test_invalid_path_raises(self):
        from genimg.utils.exceptions import ImageProcessingError

        with pytest.raises((ImageProcessingError, OSError, FileNotFoundError)):
            load_image("/nonexistent.png")


@pytest.mark.unit
class TestGetImageHash:
    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            get_image_hash("/nonexistent.png")

    def test_returns_sha256_hex(self, tmp_path):
        f = tmp_path / "x.bin"
        f.write_bytes(b"content")
        h = get_image_hash(str(f))
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


@pytest.mark.unit
class TestProcessReferenceImage:
    def test_from_bytes_returns_encoded_and_hash(self):
        png = _minimal_png_bytes()
        config = Config(openrouter_api_key="", min_image_pixels=1)
        encoded, ref_hash = process_reference_image(
            png, format_hint="PNG", config=config
        )
        assert isinstance(encoded, str)
        assert len(ref_hash) == 64
        assert ref_hash == __import__("hashlib").sha256(png).hexdigest()

    def test_from_bytes_uses_config_max_pixels(self):
        config = Config(openrouter_api_key="", min_image_pixels=1, max_image_pixels=1)
        png = _minimal_png_bytes()
        encoded, _ = process_reference_image(png, format_hint="PNG", config=config)
        assert isinstance(encoded, str)

    def test_from_path_requires_existing_file(self):
        with pytest.raises(FileNotFoundError):
            process_reference_image("/nonexistent.png")

    def test_from_path_success_returns_encoded_and_hash(self, tmp_path):
        """Process from real file path to cover load_image, get_image_hash path."""
        png = _minimal_png_bytes()
        path = tmp_path / "ref.png"
        path.write_bytes(png)
        config = Config(openrouter_api_key="", min_image_pixels=1)
        encoded, ref_hash = process_reference_image(path, config=config)
        assert isinstance(encoded, str)
        assert len(ref_hash) == 64
        assert ref_hash == get_image_hash(str(path))

    def test_from_data_url_returns_encoded_and_hash(self):
        """Process from data URL (e.g. Gradio clipboard) so image is sent to API."""
        png = _minimal_png_bytes()
        b64 = base64.b64encode(png).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"
        config = Config(openrouter_api_key="", min_image_pixels=1)
        encoded, ref_hash = process_reference_image(data_url, config=config)
        assert isinstance(encoded, str)
        assert len(ref_hash) == 64
        assert ref_hash == __import__("hashlib").sha256(png).hexdigest()

    def test_raises_when_image_below_min_image_pixels(self):
        """Process rejects image with fewer pixels than config.min_image_pixels."""
        png = _minimal_png_bytes()  # 1x1
        config = Config(openrouter_api_key="", min_image_pixels=2500)
        with pytest.raises(ValidationError) as exc_info:
            process_reference_image(png, format_hint="PNG", config=config)
        assert "too small" in str(exc_info.value)
        assert "2500" in str(exc_info.value)
        assert exc_info.value.field == "image"
