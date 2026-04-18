"""Unit tests for OpenRouter multimodal payload shape."""

import pytest

from genimg.core.providers.openrouter import OpenRouterProvider


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
