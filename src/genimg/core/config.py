"""
Configuration management for genimg.

This module handles API keys, model selection, and other configuration settings.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from genimg.logging_config import get_logger
from genimg.utils.exceptions import ConfigurationError

logger = get_logger(__name__)

# Load environment variables from .env file
load_dotenv()

# Default configuration constants
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_IMAGE_PROVIDER = "ollama"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_IMAGE_MODEL = "bytedance-seed/seedream-4.5"
DEFAULT_OPTIMIZATION_MODEL = "svjack/gpt-oss-20b-heretic"

# Provider ids accepted by validate(); do not import from genimg.core.providers (circular import)
KNOWN_IMAGE_PROVIDERS = ("openrouter", "ollama")


@dataclass
class Config:
    """Configuration for genimg application."""

    # API Configuration (openrouter_api_key excluded from repr to avoid leaking secrets)
    openrouter_api_key: str = field(default="", repr=False)
    openrouter_base_url: str = DEFAULT_OPENROUTER_BASE_URL

    # Model Configuration
    default_image_provider: str = DEFAULT_IMAGE_PROVIDER
    default_image_model: str = DEFAULT_IMAGE_MODEL
    default_optimization_model: str = DEFAULT_OPTIMIZATION_MODEL

    # Ollama (image generation when default_image_provider == "ollama")
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL

    # Image Processing Configuration
    min_image_pixels: int = 2500  # minimum total pixels for reference images
    max_image_pixels: int = 2_000_000  # 2 megapixels
    default_image_quality: int = 95  # JPEG quality for saved images
    aspect_ratio: tuple[int, int] = (
        1,
        1,
    )  # (width, height) ratio for output; images padded to match

    # Timeout Configuration (seconds)
    generation_timeout: int = 180  # 3 minutes
    optimization_timeout: int = 120  # 2 minutes

    # Debug: log raw API payload/response with image data truncated
    debug_api: bool = False

    # Runtime state
    optimization_enabled: bool = False
    _validated: bool = field(default=False, repr=False)

    @classmethod
    def from_env(cls) -> "Config":
        """
        Create a Config instance from environment variables.

        Environment variables:
            OPENROUTER_API_KEY: Required for image generation
            GENIMG_DEFAULT_MODEL: Optional default image generation model
            GENIMG_OPTIMIZATION_MODEL: Optional default optimization model
            GENIMG_MIN_IMAGE_PIXELS: Optional minimum total pixels for reference images (default 2500)

        Returns:
            Config instance populated from environment

        Raises:
            ConfigurationError: If required environment variables are missing
        """
        api_key = os.getenv("OPENROUTER_API_KEY", "")

        def _int_env(name: str, default: int) -> int:
            val = os.getenv(name)
            if val is None or val == "":
                return default
            # val is str here; mypy narrows after the None/empty check
            return int(val)

        debug_api = os.getenv("GENIMG_DEBUG_API", "").strip().lower() in ("1", "true", "yes")
        default_image_provider = os.getenv("GENIMG_DEFAULT_IMAGE_PROVIDER", DEFAULT_IMAGE_PROVIDER)
        ollama_base_url = (
            os.getenv("OLLAMA_BASE_URL")
            or os.getenv("GENIMG_OLLAMA_BASE_URL")
            or DEFAULT_OLLAMA_BASE_URL
        )

        config = cls(
            openrouter_api_key=api_key,
            default_image_provider=default_image_provider,
            default_image_model=os.getenv("GENIMG_DEFAULT_MODEL", cls.default_image_model),
            default_optimization_model=os.getenv(
                "GENIMG_OPTIMIZATION_MODEL", cls.default_optimization_model
            ),
            ollama_base_url=ollama_base_url,
            min_image_pixels=_int_env("GENIMG_MIN_IMAGE_PIXELS", 2500),
            debug_api=debug_api,
        )

        return config

    def validate(self) -> None:
        """
        Validate the configuration.

        Only the default image provider is validated here. Override at runtime
        is validated at generate time by the chosen provider.

        Raises:
            ConfigurationError: If configuration is invalid
        """
        logger.debug("Validating config")

        if self.min_image_pixels <= 0:
            raise ConfigurationError(
                f"min_image_pixels must be positive, got {self.min_image_pixels}."
            )
        if self.min_image_pixels > self.max_image_pixels:
            raise ConfigurationError(
                f"min_image_pixels ({self.min_image_pixels}) must not exceed "
                f"max_image_pixels ({self.max_image_pixels})."
            )

        ar_w, ar_h = self.aspect_ratio
        if ar_w <= 0 or ar_h <= 0:
            raise ConfigurationError(
                f"aspect_ratio components must be positive, got {self.aspect_ratio}."
            )

        provider = self.default_image_provider
        if provider not in KNOWN_IMAGE_PROVIDERS:
            raise ConfigurationError(
                f"Unknown default_image_provider: {provider!r}. "
                f"Must be one of: {', '.join(KNOWN_IMAGE_PROVIDERS)}."
            )
        if provider == "openrouter":
            if not self.openrouter_api_key:
                raise ConfigurationError(
                    "OpenRouter API key is required when default provider is openrouter. "
                    "Set OPENROUTER_API_KEY environment variable or provide it explicitly."
                )
            if not self.openrouter_api_key.startswith("sk-"):
                raise ConfigurationError(
                    "OpenRouter API key appears to be invalid. It should start with 'sk-'."
                )
        # provider == "ollama": no API key required; ollama_base_url can use default

        self._validated = True

    def is_valid(self) -> bool:
        """
        Check if configuration has been validated.

        Returns:
            True if validate() has been called successfully
        """
        return self._validated

    def set_api_key(self, api_key: str) -> None:
        """
        Set the OpenRouter API key.

        Args:
            api_key: The API key to use

        Raises:
            ConfigurationError: If API key is invalid
        """
        if not api_key:
            raise ConfigurationError("API key cannot be empty")

        if not api_key.startswith("sk-"):
            raise ConfigurationError(
                "OpenRouter API key appears to be invalid. It should start with 'sk-'."
            )

        self.openrouter_api_key = api_key
        self._validated = False  # Need to revalidate

    def set_image_model(self, model: str) -> None:
        """
        Set the default image generation model.

        Model ID format is provider-specific (e.g. OpenRouter: 'provider/name';
        Ollama: model name). Only non-empty is required here.

        Args:
            model: Model ID for the configured image provider

        Raises:
            ConfigurationError: If model is empty
        """
        if not model:
            raise ConfigurationError("Model ID cannot be empty")

        self.default_image_model = model

    def set_optimization_model(self, model: str) -> None:
        """
        Set the default prompt optimization model.

        Args:
            model: Ollama model name

        Raises:
            ConfigurationError: If model name is invalid
        """
        if not model:
            raise ConfigurationError("Model name cannot be empty")

        self.default_optimization_model = model


# Global configuration instance
_global_config: Config | None = None


def get_config() -> Config:
    """
    Get the global configuration instance.

    Returns:
        The global Config instance
    """
    global _global_config
    if _global_config is None:
        _global_config = Config.from_env()
    return _global_config


def set_config(config: Config) -> None:
    """
    Set the global configuration instance.

    Args:
        config: The Config instance to use globally
    """
    global _global_config
    _global_config = config
