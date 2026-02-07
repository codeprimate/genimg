"""Unit tests for genimg exceptions."""

import pytest

from genimg.utils.exceptions import (
    APIError,
    CancellationError,
    ConfigurationError,
    GenimgError,
    ImageProcessingError,
    NetworkError,
    RequestTimeoutError,
    ValidationError,
)


@pytest.mark.unit
class TestGenimgError:
    def test_base_is_exception(self):
        assert issubclass(GenimgError, Exception)

    def test_subclasses_are_genimg_error(self):
        for cls in (
            ValidationError,
            APIError,
            NetworkError,
            RequestTimeoutError,
            CancellationError,
            ConfigurationError,
            ImageProcessingError,
        ):
            assert issubclass(cls, GenimgError)


@pytest.mark.unit
class TestValidationError:
    def test_message_and_field(self):
        e = ValidationError("bad value", field="prompt")
        assert str(e) == "bad value"
        assert e.field == "prompt"

    def test_field_optional(self):
        e = ValidationError("invalid")
        assert e.field == ""


@pytest.mark.unit
class TestAPIError:
    def test_message_status_response(self):
        e = APIError("failed", status_code=500, response="body")
        assert e.status_code == 500
        assert e.response == "body"


@pytest.mark.unit
class TestNetworkError:
    def test_original_error(self):
        inner = ConnectionError("refused")
        e = NetworkError("network failed", original_error=inner)
        assert e.original_error is inner


@pytest.mark.unit
class TestRequestTimeoutError:
    def test_inherits_genimg_error(self):
        e = RequestTimeoutError("timed out")
        assert isinstance(e, GenimgError)


@pytest.mark.unit
class TestImageProcessingError:
    def test_image_path(self):
        e = ImageProcessingError("decode failed", image_path="/tmp/x.png")
        assert e.image_path == "/tmp/x.png"
