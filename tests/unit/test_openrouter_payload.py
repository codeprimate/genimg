"""Unit tests for OpenRouter multimodal payload shape and response parsing."""

import base64
import io

import pytest
from PIL import Image

from genimg.core.providers.openrouter import (
    OpenRouterProvider,
    _extract_image_url_from_result,
)

_MINIMAL_PNG_BUF = io.BytesIO()
Image.new("RGB", (1, 1), color=(0, 0, 0)).save(_MINIMAL_PNG_BUF, format="PNG")
MINIMAL_PNG = _MINIMAL_PNG_BUF.getvalue()


@pytest.mark.unit
def test_build_payload_text_then_n_image_parts() -> None:
    provider = OpenRouterProvider()
    refs = ["aaa", "bbb"]
    payload = provider._build_payload("hello", "m/test", refs)
    content = payload["messages"][0]["content"]
    assert len(content) == 1 + len(refs)
    assert content[0] == {"type": "text", "text": "hello"}
    assert content[1]["type"] == "image_url"
    assert "aaa" in content[1]["image_url"]["url"]
    assert content[2]["type"] == "image_url"
    assert "bbb" in content[2]["image_url"]["url"]


@pytest.mark.unit
def test_build_payload_no_refs_text_only() -> None:
    provider = OpenRouterProvider()
    payload = provider._build_payload("x", "m", None)
    assert payload["messages"][0]["content"] == [{"type": "text", "text": "x"}]


@pytest.mark.unit
def test_extract_image_url_nested_dict() -> None:
    b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
    url = f"data:image/png;base64,{b64}"
    result = {
        "choices": [
            {"message": {"images": [{"image_url": {"url": url}}]}},
        ]
    }
    assert _extract_image_url_from_result(result) == url


@pytest.mark.unit
def test_extract_image_url_when_image_url_is_string() -> None:
    """Some providers return image_url as a direct string, not {url: ...}."""
    b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
    url = f"data:image/png;base64,{b64}"
    result = {
        "choices": [
            {"message": {"images": [{"type": "image_url", "image_url": url}]}},
        ]
    }
    assert _extract_image_url_from_result(result) == url


@pytest.mark.unit
def test_extract_image_url_from_content_parts() -> None:
    b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
    url = f"data:image/png;base64,{b64}"
    result = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "done"},
                        {"type": "image_url", "image_url": {"url": url}},
                    ]
                }
            },
        ]
    }
    assert _extract_image_url_from_result(result) == url
