"""
Configuration management for genimg.

This module handles API keys, model selection, and other configuration settings.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

from genimg.utils.exceptions import ConfigurationError

# Load environment variables from .env file
load_dotenv()


@dataclass
class Config:
    """Configuration for genimg application."""

    # API Configuration
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Model Configuration
    default_image_model: str = "google/gemini-2.0-flash-exp-image:free"
    default_optimization_model: str = "llama3.2"

    # Image Processing Configuration
    max_image_pixels: int = 2_000_000  # 2 megapixels
    default_image_quality: int = 95  # JPEG quality for saved images

    # Timeout Configuration (seconds)
    generation_timeout: int = 300  # 5 minutes
    optimization_timeout: int = 120  # 2 minutes

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

        Returns:
            Config instance populated from environment

        Raises:
            ConfigurationError: If required environment variables are missing
        """
        api_key = os.getenv("OPENROUTER_API_KEY", "")

        config = cls(
            openrouter_api_key=api_key,
            default_image_model=os.getenv(
                "GENIMG_DEFAULT_MODEL", cls.default_image_model
            ),
            default_optimization_model=os.getenv(
                "GENIMG_OPTIMIZATION_MODEL", cls.default_optimization_model
            ),
        )

        return config

    def validate(self) -> None:
        """
        Validate the configuration.

        Raises:
            ConfigurationError: If configuration is invalid
        """
        if not self.openrouter_api_key:
            raise ConfigurationError(
                "OpenRouter API key is required. "
                "Set OPENROUTER_API_KEY environment variable or provide it explicitly."
            )

        if not self.openrouter_api_key.startswith("sk-"):
            raise ConfigurationError(
                "OpenRouter API key appears to be invalid. "
                "It should start with 'sk-'."
            )

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
                "OpenRouter API key appears to be invalid. "
                "It should start with 'sk-'."
            )

        self.openrouter_api_key = api_key
        self._validated = False  # Need to revalidate

    def set_image_model(self, model: str) -> None:
        """
        Set the default image generation model.

        Args:
            model: Model ID in format 'provider/model-name'

        Raises:
            ConfigurationError: If model ID is invalid
        """
        if not model:
            raise ConfigurationError("Model ID cannot be empty")

        if "/" not in model:
            raise ConfigurationError(
                "Model ID should be in format 'provider/model-name'"
            )

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
_global_config: Optional[Config] = None


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
