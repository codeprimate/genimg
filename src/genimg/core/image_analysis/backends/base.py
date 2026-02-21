"""
Abstract base for image description backends (Florence-2, JoyTag).
"""

from abc import ABC, abstractmethod


class DescribeBackend(ABC):
    """Abstract backend for describing images (caption or tags)."""

    @abstractmethod
    def is_loaded(self) -> bool:
        """Return True if the model is loaded in memory."""
        ...

    @abstractmethod
    def unload(self) -> None:
        """Release model from memory. Idempotent."""
        ...
