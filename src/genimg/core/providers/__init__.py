"""
Image generation providers: protocol, registry, and built-in implementations.

Built-in providers are registered lazily on first get_registry() call to avoid
circular imports with core.image_gen.
"""

from genimg.core.providers.base import ImageGenerationProvider as ImageGenerationProvider
from genimg.core.providers.registry import (
    ProviderRegistry,
)
from genimg.core.providers.registry import (
    get_registry as _get_registry_impl,
)
from genimg.core.provider_ids import (
    KNOWN_IMAGE_PROVIDER_IDS,
    PROVIDER_DRAW_THINGS,
    PROVIDER_OLLAMA,
    PROVIDER_OPENROUTER,
)

KNOWN_IMAGE_PROVIDERS = KNOWN_IMAGE_PROVIDER_IDS

_builtins_registered = False


def _register_builtins(reg: ProviderRegistry) -> None:
    """Register built-in providers. Called once when registry is first used."""
    global _builtins_registered
    if _builtins_registered:
        return
    from genimg.core.providers.ollama import OllamaProvider
    from genimg.core.providers.openrouter import OpenRouterProvider
    from genimg.core.providers.draw_things.provider import DrawThingsProvider

    reg.register(PROVIDER_OPENROUTER, OpenRouterProvider())
    reg.register(PROVIDER_OLLAMA, OllamaProvider())
    reg.register(PROVIDER_DRAW_THINGS, DrawThingsProvider())
    _builtins_registered = True


def get_registry() -> ProviderRegistry:
    """Return the global provider registry and ensure built-ins are registered."""
    reg = _get_registry_impl()
    _register_builtins(reg)
    return reg
