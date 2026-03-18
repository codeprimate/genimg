"""
In-memory caching for genimg.

This module provides session-scoped caching for optimized prompts to avoid
redundant API calls when the same prompt is optimized multiple times.
"""

import hashlib

from genimg.logging_config import get_logger

logger = get_logger(__name__)


class PromptCache:
    """In-memory cache for optimized prompts."""

    def __init__(self) -> None:
        """Initialize an empty cache."""
        self._cache: dict[str, str] = {}

    def _generate_key(
        self,
        prompt: str,
        model: str,
        reference_hash: str | None = None,
        description_key: str | None = None,
        use_thinking: bool = False,
    ) -> str:
        """
        Generate a cache key from prompt, model, and optional reference/description/thinking.

        When description_key is set (description-based optimization), the key is distinct
        from the non-description path. REQ-014: exact key strategy may be refined later.
        use_thinking separates cache entries for thinking vs non-thinking optimization.
        """
        key_parts = [prompt, model]
        if reference_hash:
            key_parts.append(reference_hash)
        if description_key is not None:
            key_parts.append("desc")
            key_parts.append(description_key)
        key_parts.append("think")
        key_parts.append(str(use_thinking))

        key_string = "|".join(key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def get(
        self,
        prompt: str,
        model: str,
        reference_hash: str | None = None,
        description_key: str | None = None,
        use_thinking: bool = False,
    ) -> str | None:
        """
        Retrieve an optimized prompt from cache.

        Args:
            prompt: The original prompt text
            model: The optimization model name
            reference_hash: Hash of reference image (if any)
            description_key: When set, use description-based cache key (REQ-014).
            use_thinking: When True, cache key includes thinking-on (separate from thinking-off).

        Returns:
            The cached optimized prompt, or None if not found
        """
        key = self._generate_key(prompt, model, reference_hash, description_key, use_thinking)
        hit = key in self._cache
        logger.debug("Cache get model=%s hit=%s", model, hit)
        return self._cache.get(key)

    def set(
        self,
        prompt: str,
        model: str,
        optimized_prompt: str,
        reference_hash: str | None = None,
        description_key: str | None = None,
        use_thinking: bool = False,
    ) -> None:
        """
        Store an optimized prompt in cache.

        Args:
            prompt: The original prompt text
            model: The optimization model name
            optimized_prompt: The optimized prompt to cache
            reference_hash: Hash of reference image (if any)
            description_key: When set, use description-based cache key (REQ-014).
            use_thinking: When True, cache key includes thinking-on (separate from thinking-off).
        """
        key = self._generate_key(prompt, model, reference_hash, description_key, use_thinking)
        self._cache[key] = optimized_prompt
        logger.debug("Cache set model=%s", model)

    def clear(self) -> None:
        """Clear all cached prompts."""
        self._cache.clear()

    def size(self) -> int:
        """
        Get the number of cached prompts.

        Returns:
            Number of items in cache
        """
        return len(self._cache)


# Global cache instance for the application
_global_cache: PromptCache | None = None


def get_cache() -> PromptCache:
    """
    Get the global cache instance.

    Returns:
        The global PromptCache instance
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = PromptCache()
    return _global_cache


def clear_cache() -> None:
    """Clear the global cache."""
    cache = get_cache()
    cache.clear()


def get_cached_prompt(
    prompt: str,
    model: str,
    reference_hash: str | None = None,
    use_thinking: bool = False,
) -> str | None:
    """
    Return the cached optimized prompt for the given inputs, or None if not cached.

    Args:
        prompt: The original prompt text
        model: The optimization model name
        reference_hash: Hash of reference image (if any)
        use_thinking: When True, look up cache entry for thinking-on optimization.

    Returns:
        The cached optimized prompt, or None if not in cache
    """
    return get_cache().get(prompt, model, reference_hash=reference_hash, use_thinking=use_thinking)
