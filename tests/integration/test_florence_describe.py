"""
Integration tests for Florence-2 image description (prose caption).

These tests load the real Florence backend and run captioning. No mocks.
Run with: pytest --run-slow
"""

import pytest
from PIL import Image

from genimg.core.image_analysis import describe_image, unload_describe_models


@pytest.mark.integration
@pytest.mark.slow
class TestFlorenceDescribeIntegration:
    """Real Florence-2 describe path; would have caught TokenizersBackend / additional_special_tokens bug."""

    def test_describe_image_prose_returns_string_no_mocks(self) -> None:
        """describe_image(method='prose') with real backend: load processor, run caption, return string.

        No mocks. Uses the same path as the UI Describe button. Would fail with
        AttributeError (TokenizersBackend has no attribute additional_special_tokens)
        if the processor were loaded from the hub's remote code instead of the built-in.
        """
        unload_describe_models()
        image = Image.new("RGB", (64, 64), color=(100, 150, 200))

        result = describe_image(image, method="prose", verbosity="brief")

        assert isinstance(result, str)
        assert len(result.strip()) > 0
