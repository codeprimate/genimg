"""
genimg - AI Image Generation Tool

A Python package for generating AI images with prompt optimization.
Supports multiple models via OpenRouter and local prompt optimization via Ollama.

Library usage:
- Configuration can be passed per operation (e.g. generate_image(..., config=my_config))
  or via the shared config: use get_config() / set_config() and omit the config argument.
- The prompt optimization cache is process-scoped. Use clear_cache() and get_cached_prompt()
  for "clear cache" or "refresh" behavior; use get_cache() for direct cache access.
"""

__version__ = "0.1.0"
__author__ = "Patrick Morgan"
__email__ = "patrick@sitewire.co"

from genimg.core.config import Config, get_config, set_config
from genimg.core.image_gen import GenerationResult, generate_image
from genimg.core.prompt import optimize_prompt, validate_prompt
from genimg.core.reference import process_reference_image
from genimg.utils.cache import clear_cache, get_cache, get_cached_prompt
from genimg.utils.exceptions import (
    APIError,
    CancellationError,
    ConfigurationError,
    GenimgError,
    ImageProcessingError,
    NetworkError,
    RequestTimeoutError,
    ValidationError,
)

__all__ = [
    "APIError",
    "CancellationError",
    "Config",
    "ConfigurationError",
    "GenerationResult",
    "GenimgError",
    "ImageProcessingError",
    "NetworkError",
    "RequestTimeoutError",
    "ValidationError",
    "clear_cache",
    "generate_image",
    "get_cached_prompt",
    "get_cache",
    "get_config",
    "optimize_prompt",
    "process_reference_image",
    "set_config",
    "validate_prompt",
]
