"""
Prompt management and optimization for genimg.

This module handles prompt validation, optimization via Ollama, and caching.
"""

import subprocess
import threading
from typing import Callable, List, Optional, Tuple, Union

from genimg.core.config import Config, get_config
from genimg.core.prompts_loader import get_optimization_template
from genimg.utils.cache import PromptCache, get_cache
from genimg.utils.exceptions import APIError, CancellationError, RequestTimeoutError, ValidationError

# Loaded from prompts.yaml; kept as name for backward compatibility and tests
OPTIMIZATION_TEMPLATE = get_optimization_template()


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
    config: Optional[Config] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    """
    Optimize a prompt using Ollama.

    Args:
        prompt: The original prompt to optimize
        model: The Ollama model to use (defaults to config value)
        reference_hash: Hash of reference image if present (for caching)
        timeout: Timeout in seconds (defaults to config value)
        config: Optional config to use; if None, uses shared config from get_config()
        cancel_check: Optional callable returning True to cancel; polled during the run.
            Should return quickly and not raise (exceptions are caught and ignored).

    Returns:
        Optimized prompt

    Raises:
        ValidationError: If prompt is invalid
        APIError: If Ollama is not available or optimization fails
        RequestTimeoutError: If operation times out
        CancellationError: If cancel_check returned True
    """
    validate_prompt(prompt)

    config = config or get_config()
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

    # Prepare the optimization prompt (template loaded from prompts.yaml)
    optimization_prompt = get_optimization_template().format(original_prompt=prompt)

    if cancel_check is None:
        return _run_ollama_sync(prompt, model, reference_hash, timeout, optimization_prompt, cache)

    # Run with cancellation support: subprocess in a thread, main thread polls cancel_check
    result_holder: List[Optional[Tuple[str, str]]] = [None]
    exc_holder: List[Optional[BaseException]] = [None]
    process_holder: List[Optional[subprocess.Popen[str]]] = [None]

    def worker_with_process() -> None:
        try:
            process = subprocess.Popen(
                ["ollama", "run", model],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            process_holder[0] = process
            stdout, stderr = process.communicate(input=optimization_prompt, timeout=timeout)
            result_holder[0] = (stdout, stderr)
        except subprocess.TimeoutExpired:
            if process_holder[0]:
                process_holder[0].kill()
            exc_holder[0] = RequestTimeoutError(
                f"Optimization timed out after {timeout} seconds. "
                "Try a simpler prompt or increase the timeout."
            )
        except BaseException as e:
            exc_holder[0] = e

    thread = threading.Thread(target=worker_with_process, daemon=True)
    thread.start()

    poll_interval = 0.25
    cancelled = False
    while True:
        thread.join(timeout=poll_interval)
        if not thread.is_alive():
            break
        try:
            if cancel_check():
                cancelled = True
                break
        except Exception:
            pass  # Don't let a buggy cancel_check break the loop
    if cancelled:
        proc = process_holder[0]
        if proc is not None:
            proc.terminate()
            thread.join(timeout=5.0)
        raise CancellationError("Optimization was cancelled.")

    if exc_holder[0] is not None:
        raise exc_holder[0]

    stdout, stderr = result_holder[0] or ("", "")
    process = process_holder[0]
    if process is not None and process.returncode != 0:
        raise APIError(
            f"Ollama optimization failed: {stderr}",
            status_code=process.returncode,
            response=stderr,
        )
    optimized = (stdout or "").strip()
    if not optimized:
        raise APIError("Ollama returned an empty response")
    cache.set(prompt, model, optimized, reference_hash)
    return optimized


def _run_ollama_communicate(
    model: str, optimization_prompt: str, timeout: int
) -> Tuple[str, str]:
    """Run ollama in a subprocess and return (stdout, stderr). Used by sync and worker."""
    process = subprocess.Popen(
        ["ollama", "run", model],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(input=optimization_prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        raise RequestTimeoutError(
            f"Optimization timed out after {timeout} seconds. "
            "Try a simpler prompt or increase the timeout."
        )
    if process.returncode != 0:
        raise APIError(
            f"Ollama optimization failed: {stderr}",
            status_code=process.returncode,
            response=stderr,
        )
    return stdout, stderr


def _run_ollama_sync(
    prompt: str,
    model: str,
    reference_hash: Optional[str],
    timeout: int,
    optimization_prompt: str,
    cache: PromptCache,
) -> str:
    """Run Ollama without cancellation; used when cancel_check is None."""
    try:
        stdout, stderr = _run_ollama_communicate(model, optimization_prompt, timeout)
    except FileNotFoundError as e:
        raise APIError(
            "Ollama command not found. Please ensure Ollama is installed and in your PATH."
        ) from e
    optimized = stdout.strip()
    if not optimized:
        raise APIError("Ollama returned an empty response")
    cache.set(prompt, model, optimized, reference_hash)
    return optimized


def optimize_prompt(
    prompt: str,
    model: Optional[str] = None,
    reference_hash: Optional[str] = None,
    enable_cache: bool = True,
    config: Optional[Config] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    """
    Optimize a prompt (main entry point).

    Args:
        prompt: The original prompt to optimize
        model: The optimization model to use (defaults to config)
        reference_hash: Hash of reference image if present
        enable_cache: Whether to use caching (default: True)
        config: Optional config to use; if None, uses shared config from get_config()
        cancel_check: Optional callable returning True to cancel; polled during the run.
            Should return quickly and not raise (exceptions are caught and ignored).

    Returns:
        Optimized prompt

    Raises:
        ValidationError: If prompt is invalid
        APIError: If optimization fails
        RequestTimeoutError: If operation times out
        CancellationError: If cancel_check returned True
    """
    validate_prompt(prompt)

    config = config or get_config()

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
    return optimize_prompt_with_ollama(
        prompt, model, reference_hash, config=config, cancel_check=cancel_check
    )
