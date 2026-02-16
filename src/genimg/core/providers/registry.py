"""
Registry for image generation providers.

Maps provider ids (e.g. "openrouter", "ollama") to provider implementations.
"""

from genimg.core.providers.base import ImageGenerationProvider


class ProviderRegistry:
    """Registry mapping provider id to ImageGenerationProvider implementation."""

    def __init__(self) -> None:
        self._impls: dict[str, ImageGenerationProvider] = {}

    def register(self, provider_id: str, impl: ImageGenerationProvider) -> None:
        """Register a provider implementation. Idempotent for the same id."""
        self._impls[provider_id] = impl

    def get(self, provider_id: str) -> ImageGenerationProvider | None:
        """Return the registered implementation for provider_id, or None if unknown."""
        return self._impls.get(provider_id)

    def provider_ids(self) -> list[str]:
        """Return the list of registered provider ids."""
        return list(self._impls.keys())


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    """Return the global provider registry. Creates it on first call."""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
