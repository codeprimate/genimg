"""Unit tests for the provider registry and built-in registration."""

import pytest

from genimg.core.providers import (
    KNOWN_IMAGE_PROVIDERS,
    PROVIDER_OLLAMA,
    PROVIDER_OPENROUTER,
    get_registry,
)


@pytest.mark.unit
class TestProviderRegistry:
    def test_get_openrouter_returns_implementation(self):
        reg = get_registry()
        impl = reg.get(PROVIDER_OPENROUTER)
        assert impl is not None
        assert getattr(impl, "supports_reference_image", None) is True

    def test_get_ollama_returns_implementation(self):
        reg = get_registry()
        impl = reg.get(PROVIDER_OLLAMA)
        assert impl is not None
        assert getattr(impl, "supports_reference_image", None) is False

    def test_get_unknown_returns_none(self):
        reg = get_registry()
        assert reg.get("unknown") is None

    def test_provider_ids_contains_builtins(self):
        reg = get_registry()
        ids = reg.provider_ids()
        assert PROVIDER_OPENROUTER in ids
        assert PROVIDER_OLLAMA in ids
        assert len(ids) >= 2

    def test_known_image_providers_constant(self):
        assert PROVIDER_OPENROUTER in KNOWN_IMAGE_PROVIDERS
        assert PROVIDER_OLLAMA in KNOWN_IMAGE_PROVIDERS
