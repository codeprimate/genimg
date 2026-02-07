"""
Prompt management and optimization for genimg.

This module handles prompt validation, optimization via Ollama, and caching.
"""

import subprocess
import time
from typing import Optional

from genimg.core.config import get_config
from genimg.utils.cache import get_cache
from genimg.utils.exceptions import APIError, CancellationError, ValidationError

# Prompt optimization template
OPTIMIZATION_TEMPLATE = """You are a professional prompt engineer for AI image generation. Your task is to enhance the user's prompt to produce better, more detailed images.

User's original prompt:
{original_prompt}

Please enhance this prompt by:
1. Adding technical photography details (camera angle, lighting, composition) if applicable
2. Clarifying spatial relationships and scene layout
3. Specifying style and artistic qualities
4. Adding relevant details that match the intent
5. Structuring the information clearly

IMPORTANT: If the prompt mentions a reference image, preserve those instructions EXACTLY as written.

Return ONLY the enhanced prompt, without any explanations or meta-commentary."""


def validate_prompt(prompt: str) -> None:
    """
    Validate a text prompt.

    Args:
        prompt: The prompt to validate

    Raises:
        ValidationError: If prompt is invalid
    """
    if not prompt or not prompt.strip():
        raise ValidationError("Prompt cannot be empty", field="prompt")

    if len(prompt.strip()) < 3:
        raise ValidationError(
            "Prompt is too short. Please provide at least 3 characters.",
            field="prompt",
        )


def check_ollama_available() -> bool:
    """
    Check if Ollama is available on the system.

    Returns:
        True if Ollama is available, False otherwise
    """
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def optimize_prompt_with_ollama(
    prompt: str,
    model: Optional[str] = None,
    reference_hash: Optional[str] = None,
    timeout: Optional[int] = None,
) -> str:
    """
    Optimize a prompt using Ollama.

    Args:
        prompt: The original prompt to optimize
        model: The Ollama model to use (defaults to config value)
        reference_hash: Hash of reference image if present (for caching)
        timeout: Timeout in seconds (defaults to config value)

    Returns:
        Optimized prompt

    Raises:
        ValidationError: If prompt is invalid
        APIError: If Ollama is not available or optimization fails
        CancellationError: If operation times out
    """
    validate_prompt(prompt)

    config = get_config()
    if model is None:
        model = config.default_optimization_model

    if timeout is None:
        timeout = config.optimization_timeout

    # Check cache first
    cache = get_cache()
    cached = cache.get(prompt, model, reference_hash)
    if cached:
        return cached

    # Check if Ollama is available
    if not check_ollama_available():
        raise APIError(
            "Ollama is not available. Please install Ollama and ensure it's in your PATH. "
            "Visit https://ollama.ai for installation instructions."
        )

    # Prepare the optimization prompt
    optimization_prompt = OPTIMIZATION_TEMPLATE.format(original_prompt=prompt)

    try:
        # Run Ollama
        start_time = time.time()
        process = subprocess.Popen(
            ["ollama", "run", model],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stdout, stderr = process.communicate(
            input=optimization_prompt, timeout=timeout
        )

        elapsed = time.time() - start_time

        if process.returncode != 0:
            raise APIError(
                f"Ollama optimization failed: {stderr}",
                status_code=process.returncode,
                response=stderr,
            )

        optimized = stdout.strip()

        if not optimized:
            raise APIError("Ollama returned an empty response")

        # Cache the result
        cache.set(prompt, model, optimized, reference_hash)

        return optimized

    except subprocess.TimeoutExpired:
        process.kill()
        raise CancellationError(
            f"Optimization timed out after {timeout} seconds. "
            "Try a simpler prompt or increase the timeout."
        )

    except FileNotFoundError:
        raise APIError(
            "Ollama command not found. Please ensure Ollama is installed and in your PATH."
        )

    except Exception as e:
        raise APIError(f"Optimization failed: {str(e)}") from e


def optimize_prompt(
    prompt: str,
    model: Optional[str] = None,
    reference_hash: Optional[str] = None,
    enable_cache: bool = True,
) -> str:
    """
    Optimize a prompt (main entry point).

    Args:
        prompt: The original prompt to optimize
        model: The optimization model to use (defaults to config)
        reference_hash: Hash of reference image if present
        enable_cache: Whether to use caching (default: True)

    Returns:
        Optimized prompt

    Raises:
        ValidationError: If prompt is invalid
        APIError: If optimization fails
        CancellationError: If operation is cancelled
    """
    validate_prompt(prompt)

    config = get_config()

    # If optimization is disabled, return original
    if not config.optimization_enabled:
        return prompt

    # Check cache if enabled
    if enable_cache:
        cache = get_cache()
        if model is None:
            model = config.default_optimization_model
        cached = cache.get(prompt, model, reference_hash)
        if cached:
            return cached

    # Perform optimization
    return optimize_prompt_with_ollama(prompt, model, reference_hash)
