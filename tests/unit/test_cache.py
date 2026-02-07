"""Unit tests for cache."""

import pytest

from genimg.utils.cache import (
    PromptCache,
    clear_cache,
    get_cache,
    get_cached_prompt,
)


@pytest.mark.unit
class TestPromptCache:
    def test_get_miss_returns_none(self):
        cache = PromptCache()
        assert cache.get("prompt", "model") is None
        assert cache.get("prompt", "model", "refhash") is None

    def test_set_get_roundtrip(self):
        cache = PromptCache()
        cache.set("p", "m", "optimized", reference_hash=None)
        assert cache.get("p", "m") == "optimized"

    def test_set_get_with_reference_hash(self):
        cache = PromptCache()
        cache.set("p", "m", "opt2", reference_hash="abc")
        assert cache.get("p", "m", "abc") == "opt2"
        assert cache.get("p", "m") is None

    def test_clear_removes_all(self):
        cache = PromptCache()
        cache.set("p", "m", "x")
        cache.clear()
        assert cache.get("p", "m") is None
        assert cache.size() == 0

    def test_size(self):
        cache = PromptCache()
        assert cache.size() == 0
        cache.set("p1", "m", "x")
        assert cache.size() == 1
        cache.set("p2", "m", "y")
        assert cache.size() == 2


@pytest.mark.unit
class TestGetCachedPrompt:
    def test_returns_none_when_empty(self):
        clear_cache()
        assert get_cached_prompt("any", "model") is None

    def test_returns_cached_value(self):
        cache = get_cache()
        cache.clear()
        cache.set("prompt", "model", "optimized")
        assert get_cached_prompt("prompt", "model") == "optimized"
        clear_cache()
