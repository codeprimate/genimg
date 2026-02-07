"""
In-memory caching for genimg.

This module provides session-scoped caching for optimized prompts to avoid
redundant API calls when the same prompt is optimized multiple times.
"""

import hashlib
from typing import Dict, Optional


class PromptCache:
    """In-memory cache for optimized prompts."""

    def __init__(self) -> None:
        """Initialize an empty cache."""
        self._cache: Dict[str, str] = {}

    def _generate_key(
        self, prompt: str, model: str, reference_hash: Optional[str] = None
    ) -> str:
        """
        Generate a cache key from prompt, model, and optional reference image hash.

        Args:
            prompt: The original prompt text
            model: The optimization model name
            reference_hash: Hash of reference image (if any)

        Returns:
            A hash string to use as cache key
        """
        key_parts = [prompt, model]
        if reference_hash:
            key_parts.append(reference_hash)

        key_string = "|".join(key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def get(
        self, prompt: str, model: str, reference_hash: Optional[str] = None
    ) -> Optional[str]:
        """
        Retrieve an optimized prompt from cache.

        Args:
            prompt: The original prompt text
            model: The optimization model name
            reference_hash: Hash of reference image (if any)

        Returns:
            The cached optimized prompt, or None if not found
        """
        key = self._generate_key(prompt, model, reference_hash)
        return self._cache.get(key)

    def set(
        self,
        prompt: str,
        model: str,
        optimized_prompt: str,
        reference_hash: Optional[str] = None,
    ) -> None:
        """
        Store an optimized prompt in cache.

        Args:
            prompt: The original prompt text
            model: The optimization model name
            optimized_prompt: The optimized prompt to cache
            reference_hash: Hash of reference image (if any)
        """
        key = self._generate_key(prompt, model, reference_hash)
        self._cache[key] = optimized_prompt

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
_global_cache: Optional[PromptCache] = None


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
