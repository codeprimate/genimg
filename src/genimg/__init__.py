"""
genimg - AI Image Generation Tool

A Python package for generating AI images with prompt optimization.
Supports multiple models via OpenRouter and local prompt optimization via Ollama.
"""

__version__ = "0.1.0"
__author__ = "Patrick Morgan"
__email__ = "patrick@sitewire.co"

from genimg.core.config import Config
from genimg.core.image_gen import generate_image
from genimg.core.prompt import optimize_prompt
from genimg.utils.exceptions import (
    APIError,
    CancellationError,
    NetworkError,
    ValidationError,
)

__all__ = [
    "Config",
    "generate_image",
    "optimize_prompt",
    "APIError",
    "CancellationError",
    "NetworkError",
    "ValidationError",
]
