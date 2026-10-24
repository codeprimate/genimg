"""Unit tests for OpenRouter multimodal payload shape and response parsing."""

import base64
import inspect
import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from genimg.core.config import Config
from genimg.core.providers.openrouter import (
    OpenRouterProvider,
    _extract_image_url_from_result,
)

_SIZE_FIELD_NAMES = frozenset(
    {"width", "height", "aspect_ratio", "aspectRatio", "resolution", "image_config"}
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
    assert set(payload) == {"model", "modalities", "messages"}
    assert payload["messages"][0]["content"] == [{"type": "text", "text": "x"}]
    names = [
        name
        for name in inspect.signature(OpenRouterProvider._build_payload).parameters
        if name != "self"
    ]
    assert names == ["prompt", "model", "reference_images_b64"]


@pytest.mark.unit
def test_generate_with_size_pair_posts_no_size_fields() -> None:
    config = Config(openrouter_api_key="sk-ok", default_image_provider="openrouter")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers.get.return_value = "image/png"
    mock_response.content = MINIMAL_PNG
    mock_response.text = ""
    with patch(
        "genimg.core.providers.openrouter.requests.post", return_value=mock_response
    ) as posted:
        OpenRouterProvider().generate(
            "a cat",
            "m/test",
            None,
            30,
            config,
            None,
            aspect_ratio="16:9",
            max_extent=1024,
        )
    body = posted.call_args.kwargs["json"]
    assert set(body) == {"model", "modalities", "messages"}
    assert _SIZE_FIELD_NAMES.isdisjoint(body)


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
