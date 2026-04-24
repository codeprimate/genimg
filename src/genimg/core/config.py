"""
Configuration management for genimg.

This module handles API keys, model selection, and other configuration settings.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from genimg.core.provider_ids import KNOWN_IMAGE_PROVIDER_IDS, PROVIDER_DRAW_THINGS
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
DEFAULT_OPTIMIZATION_MODEL = "huihui_ai/qwen3.5-abliterated:4b"
DEFAULT_DRAW_THINGS_HOST = "127.0.0.1"
DEFAULT_DRAW_THINGS_PORT = 7859
DEFAULT_DRAW_THINGS_PRESET = "z-image"

# Provider ids accepted by validate(); sourced from neutral provider_ids module.
KNOWN_IMAGE_PROVIDERS = KNOWN_IMAGE_PROVIDER_IDS


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

    # Draw Things (image generation when provider == "draw_things")
    draw_things_host: str = DEFAULT_DRAW_THINGS_HOST
    draw_things_port: int = DEFAULT_DRAW_THINGS_PORT
    draw_things_use_tls: bool = True
    draw_things_insecure: bool = False
    draw_things_shared_secret: str | None = None
    draw_things_root_ca_pem_path: Path | None = None
    default_draw_things_image_model: str = ""
    draw_things_preset: str = DEFAULT_DRAW_THINGS_PRESET
    draw_things_width_px: int | None = None
    draw_things_height_px: int | None = None
    draw_things_steps: int | None = None
    draw_things_guidance_scale: float | None = None
    draw_things_strength: float | None = None
    draw_things_sampler: int | None = None
    draw_things_hires_fix: bool | None = None
    draw_things_upscaler: str | None = None
    draw_things_upscaler_scale_factor: int | None = None

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

    # Ollama thinking: when True, optimization uses LLM thinking (slower); when False (default), pass think=false for speed
    optimize_thinking: bool = False

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
            GENIMG_OPTIMIZE_THINKING: Optional enable LLM thinking during optimization (1/true/yes; default off)
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

        def _bool_env(name: str, default: bool) -> bool:
            val = os.getenv(name)
            if val is None or val == "":
                return default
            return val.strip().lower() in ("1", "true", "yes")

        def _opt_int_env(name: str) -> int | None:
            val = os.getenv(name)
            if val is None or val == "":
                return None
            return int(val)

        def _opt_float_env(name: str) -> float | None:
            val = os.getenv(name)
            if val is None or val == "":
                return None
            return float(val)

        def _opt_bool_env(name: str) -> bool | None:
            val = os.getenv(name)
            if val is None or val == "":
                return None
            return val.strip().lower() in ("1", "true", "yes")

        def _opt_str_env(name: str) -> str | None:
            val = os.getenv(name)
            if val is None:
                return None
            v = val.strip()
            return v if v else None

        debug_api = _bool_env("GENIMG_DEBUG_API", False)
        optimize_thinking = _bool_env(
            "GENIMG_OPTIMIZE_THINKING",
            _bool_env("OLLAMA_OPTIMIZE_THINKING", False),
        )
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
            draw_things_host=(
                os.getenv("GENIMG_DRAW_THINGS_HOST", cls.draw_things_host).strip()
                or DEFAULT_DRAW_THINGS_HOST
            ),
            draw_things_port=_int_env("GENIMG_DRAW_THINGS_PORT", cls.draw_things_port),
            draw_things_use_tls=_bool_env("GENIMG_DRAW_THINGS_USE_TLS", cls.draw_things_use_tls),
            draw_things_insecure=_bool_env("GENIMG_DRAW_THINGS_INSECURE", cls.draw_things_insecure),
            draw_things_shared_secret=_opt_str_env("GENIMG_DRAW_THINGS_SHARED_SECRET"),
            draw_things_root_ca_pem_path=(
                Path(ca_path)
                if (ca_path := _opt_str_env("GENIMG_DRAW_THINGS_ROOT_CA_PEM_PATH")) is not None
                else None
            ),
            default_draw_things_image_model=(
                os.getenv(
                    "GENIMG_DRAW_THINGS_DEFAULT_MODEL",
                    cls.default_draw_things_image_model,
                ).strip()
            ),
            draw_things_preset=(
                os.getenv("GENIMG_DRAW_THINGS_PRESET", cls.draw_things_preset).strip()
                or DEFAULT_DRAW_THINGS_PRESET
            ),
            draw_things_width_px=_opt_int_env("GENIMG_DRAW_THINGS_WIDTH_PX"),
            draw_things_height_px=_opt_int_env("GENIMG_DRAW_THINGS_HEIGHT_PX"),
            draw_things_steps=_opt_int_env("GENIMG_DRAW_THINGS_STEPS"),
            draw_things_guidance_scale=_opt_float_env("GENIMG_DRAW_THINGS_GUIDANCE_SCALE"),
            draw_things_strength=_opt_float_env("GENIMG_DRAW_THINGS_STRENGTH"),
            draw_things_sampler=_opt_int_env("GENIMG_DRAW_THINGS_SAMPLER"),
            draw_things_hires_fix=_opt_bool_env("GENIMG_DRAW_THINGS_HIRES_FIX"),
            draw_things_upscaler=_opt_str_env("GENIMG_DRAW_THINGS_UPSCALER"),
            draw_things_upscaler_scale_factor=_opt_int_env(
                "GENIMG_DRAW_THINGS_UPSCALER_SCALE_FACTOR"
            ),
            min_image_pixels=_int_env("GENIMG_MIN_IMAGE_PIXELS", 2500),
            optimize_thinking=optimize_thinking,
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
        elif provider == PROVIDER_DRAW_THINGS:
            if not self.draw_things_host.strip():
                raise ConfigurationError(
                    "Draw Things host is required when default provider is draw_things."
                )
            if self.draw_things_port < 1 or self.draw_things_port > 65535:
                raise ConfigurationError(
                    f"Draw Things port must be between 1 and 65535, got {self.draw_things_port}."
                )
            if self.draw_things_use_tls and not self.draw_things_insecure:
                if self.draw_things_root_ca_pem_path is not None and (
                    not self.draw_things_root_ca_pem_path.is_file()
                ):
                    raise ConfigurationError(
                        "Draw Things root CA PEM path does not exist or is not a file: "
                        f"{self.draw_things_root_ca_pem_path}"
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
