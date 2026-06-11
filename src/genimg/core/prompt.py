"""
Prompt management and optimization for genimg.

This module handles prompt validation, optimization via the Ollama HTTP API, and caching.
"""

import json
import re
import threading
import time
import warnings
from collections.abc import Callable

import requests

from genimg.core.config import DEFAULT_OLLAMA_BASE_URL, Config, get_config
from genimg.core.prompts_loader import (
    get_optimization_template,
    get_optimization_template_json,
    get_optimization_template_with_description,
    get_optimization_template_with_description_json,
)
from genimg.logging_config import get_logger, log_prompts
from genimg.utils.cache import get_cache
from genimg.utils.exceptions import (
    APIError,
    CancellationError,
    RequestTimeoutError,
    ValidationError,
)

logger = get_logger(__name__)

# Max prompt length for logging (large so prompts are effectively never truncated)
_PROMPT_LOG_MAX = 50_000

# Loaded from prompts.yaml; kept as name for backward compatibility and tests
OPTIMIZATION_TEMPLATE = get_optimization_template()

# Markers used by Ollama "thinking" models; strip this block from optimization output.
_THINKING_START = "Thinking..."
_THINKING_END = "...done thinking."

# Legacy: Ollama CLI could emit CSI sequences when stdout was not a TTY; API responses may
# still include terminal styling in rare cases, so we strip them in post-processing.
_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _strip_ansi_terminal_sequences(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", text)


def _assemble_ideogram_json(data: dict) -> str:
    """
    Assemble an Ideogram 4 JSON caption dict into a prose string for image models.

    Joins high_level_description, style cues, background, and element descriptions
    with double newlines. Returns the assembled string, or an empty string if no
    content could be extracted.
    """
    parts: list[str] = []

    if hld := data.get("high_level_description"):
        parts.append(str(hld).strip())

    sd = data.get("style_description")
    if isinstance(sd, dict):
        style_cues: list[str] = []
        for field in ("aesthetics", "lighting", "photo", "art_style", "medium"):
            val = sd.get(field)
            if val and isinstance(val, str):
                style_cues.append(val.strip())
        if style_cues:
            parts.append(", ".join(style_cues))

    cd = data.get("compositional_deconstruction")
    if isinstance(cd, dict):
        if bg := cd.get("background"):
            parts.append(str(bg).strip())
        for el in cd.get("elements") or []:
            if not isinstance(el, dict):
                continue
            desc = (el.get("desc") or "").strip()
            if el.get("type") == "text":
                text_val = (el.get("text") or "").strip()
                if text_val and desc:
                    parts.append(f'Text reading "{text_val}": {desc}')
                elif text_val:
                    parts.append(f'Text reading "{text_val}"')
                elif desc:
                    parts.append(desc)
            elif desc:
                parts.append(desc)

    return "\n\n".join(p for p in parts if p)


# Injected into the optimization template when a reference image is present (reference_hash is set).
REFERENCE_IMAGE_INSTRUCTION = """
CRITICAL: Reference images are being provided with this prompt. When optimizing:
- You cannot see or analyze these images. Do not make any assumptions about them.
- Preserve ALL instructions about how to use, modify, or reference the provided images EXACTLY as specified
- Do not change, remove, or reinterpret any image reference instructions
- Maintain the exact relationship between the prompt text and the reference images
- If the prompt specifies transformations, edits, or specific ways to use the images, keep those instructions verbatim
- Only enhance the prompt by adding complementary details that don't conflict with image reference instructions
"""


def _strip_ollama_thinking(text: str) -> str:
    """
    Remove thinking block and optional markdown code fences from Ollama output.

    Some Ollama models (e.g. thinking models) wrap reasoning in "Thinking..." ...
    "...done thinking." and may wrap the final answer in ```. This strips those
    so the returned string is the actual optimized prompt.
    """
    if not text or not text.strip():
        return text
    optimized = _strip_ansi_terminal_sequences(text).strip()
    if not optimized:
        return ""
    if _THINKING_START in optimized:
        start_idx = optimized.find(_THINKING_START)
        end_idx = optimized.find(_THINKING_END, start_idx)
        if end_idx != -1:
            before = optimized[:start_idx].strip()
            after = optimized[end_idx + len(_THINKING_END) :].strip()
            optimized = (before + " " + after).strip()
        else:
            optimized = optimized[:start_idx].strip()
    if optimized.startswith("```"):
        lines = optimized.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        optimized = "\n".join(lines).strip()
    return optimized


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


def _ollama_api_base(config: Config | None = None) -> str:
    """Base URL for Ollama HTTP API (no trailing slash)."""
    cfg = config or get_config()
    base = (cfg.ollama_base_url or DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")
    return base or DEFAULT_OLLAMA_BASE_URL.rstrip("/")


def check_ollama_available(config: Config | None = None) -> bool:
    """
    Check if the Ollama HTTP API is reachable.

    Uses GET ``/api/tags`` on the configured base URL (``OLLAMA_BASE_URL`` /
    ``GENIMG_OLLAMA_BASE_URL``).

    Returns:
        True if Ollama responds successfully, False otherwise
    """
    url = f"{_ollama_api_base(config)}/api/tags"
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def list_ollama_models(config: Config | None = None) -> list[str]:
    """
    List installed Ollama models via the HTTP API (``GET /api/tags``).

    Returns:
        List of installed model names. Returns empty list if Ollama is not available
        or the request fails.
    """
    cfg = config or get_config()
    if not check_ollama_available(cfg):
        return []

    url = f"{_ollama_api_base(cfg)}/api/tags"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return []
        data = response.json()
    except (requests.RequestException, ValueError, TypeError):
        return []

    raw_models = data.get("models")
    if not isinstance(raw_models, list):
        return []

    models: list[str] = []
    for entry in raw_models:
        if not isinstance(entry, dict):
            continue
        model_name = entry.get("name")
        if not model_name or not isinstance(model_name, str):
            continue
        model_name = model_name.strip()
        if not model_name:
            continue
        if model_name.endswith(":latest"):
            model_name = model_name[:-7]
        models.append(model_name)

    return models


_OLLAMA_IMAGE_NAMESPACES = ("x/", "my/")


def list_ollama_image_models() -> list[str]:
    """
    List installed Ollama image-generation models.

    Filters all installed models to those whose name starts with a known
    image-generation namespace (``x/`` or ``my/``).

    Returns:
        List of image model names. Returns empty list if Ollama is not available
        or no matching models are installed.
    """
    return [m for m in list_ollama_models() if m.startswith(_OLLAMA_IMAGE_NAMESPACES)]


def optimize_prompt_with_ollama(
    prompt: str,
    model: str | None = None,
    reference_hash: str | None = None,
    reference_description: str | None = None,
    timeout: int | None = None,
    config: Config | None = None,
    cancel_check: Callable[[], bool] | None = None,
    force_refresh: bool = False,
) -> str:
    """
    Optimize a prompt using Ollama.

    Args:
        prompt: The original prompt to optimize
        model: The Ollama model to use (defaults to config value)
        reference_hash: Hash of reference image if present (for caching)
        reference_description: When set, use description-based template (REQ-014 cache key)
        timeout: Timeout in seconds (defaults to config value)
        config: Optional config to use; if None, uses shared config from get_config()
        cancel_check: Optional callable returning True to cancel; polled during the run.
            Should return quickly and not raise (exceptions are caught and ignored).
        force_refresh: If True, skip cache lookup and always run Ollama (result is still cached).

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

    cache = get_cache()
    use_thinking = config.optimize_thinking
    optimize_format = config.optimize_format
    # REQ-014: description-based path uses description_key (reference_hash or description id)
    description_key = reference_hash if reference_description else None
    if not force_refresh:
        cached = cache.get(
            prompt,
            model,
            reference_hash,
            description_key=description_key,
            use_thinking=use_thinking,
            optimize_format=optimize_format,
        )
        if cached:
            logger.debug("Cache hit for model=%s", model)
            logger.info("Optimized (from cache) model=%s", model)
            return cached

    logger.debug("Cache miss for model=%s running Ollama timeout=%s", model, timeout)
    logger.info("Optimizing prompt model=%s", model)
    if log_prompts():
        truncated = prompt if len(prompt) <= _PROMPT_LOG_MAX else prompt[:_PROMPT_LOG_MAX] + "..."
        logger.info("Original prompt: %s", truncated)

    # Check if Ollama HTTP API is reachable
    if not check_ollama_available(config):
        raise APIError(
            "Ollama is not available. Start the Ollama app or daemon and ensure "
            "OLLAMA_BASE_URL / GENIMG_OLLAMA_BASE_URL points at your server "
            f"(default {DEFAULT_OLLAMA_BASE_URL}). Visit https://ollama.ai for installation."
        )

    # Prepare the optimization prompt: select template based on format and description presence
    if optimize_format == "json":
        if reference_description is not None:
            system_part = get_optimization_template_with_description_json().format(
                reference_description=reference_description
            )
        else:
            reference_instruction = REFERENCE_IMAGE_INSTRUCTION if reference_hash else ""
            system_part = get_optimization_template_json().format(
                reference_image_instruction=reference_instruction
            )
    elif reference_description is not None:
        system_part = get_optimization_template_with_description().format(
            reference_description=reference_description
        )
    else:
        reference_instruction = REFERENCE_IMAGE_INSTRUCTION if reference_hash else ""
        system_part = get_optimization_template().format(
            reference_image_instruction=reference_instruction
        )
    optimization_prompt = system_part + "\n\nOriginal prompt: " + prompt + "\n\nImproved prompt:"

    start_time = time.time()
    if cancel_check is None:
        raw = _call_ollama_generate_api(
            config, model, optimization_prompt, timeout, use_thinking, optimize_format
        )
        optimized = _post_process_ollama_response(raw, optimize_format)
        if not optimized:
            raise APIError("Ollama returned an empty response")
        cache.set(
            prompt,
            model,
            optimized,
            reference_hash,
            description_key=description_key,
            use_thinking=use_thinking,
            optimize_format=optimize_format,
        )
        elapsed = time.time() - start_time
        logger.info("Optimized in %.1fs model=%s", elapsed, model)
        if log_prompts():
            truncated = (
                optimized if len(optimized) <= _PROMPT_LOG_MAX else optimized[:_PROMPT_LOG_MAX] + "..."
            )
            logger.info("Optimized prompt: %s", truncated)
        return optimized

    # Run with cancellation support: HTTP request in a thread, main thread polls cancel_check
    result_holder: list[str | None] = [None]
    exc_holder: list[BaseException | None] = [None]

    def worker_http() -> None:
        try:
            result_holder[0] = _call_ollama_generate_api(
                config, model, optimization_prompt, timeout, use_thinking, optimize_format
            )
        except BaseException as e:
            exc_holder[0] = e

    thread = threading.Thread(target=worker_http, daemon=True)
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
        except KeyboardInterrupt:
            # Re-raise system exceptions to allow proper signal handling
            raise
        except Exception as e:
            # Log user errors but don't break the loop
            warnings.warn(
                f"cancel_check raised exception (ignored): {e!r}",
                category=RuntimeWarning,
                stacklevel=2,
            )
    if cancelled:
        # Same pattern as Ollama image provider: in-flight HTTP may continue on a daemon thread.
        raise CancellationError("Optimization was cancelled.")

    if exc_holder[0] is not None:
        raise exc_holder[0]

    raw = result_holder[0] or ""
    optimized = _post_process_ollama_response(raw, optimize_format)
    if not optimized:
        raise APIError("Ollama returned an empty response")
    cache.set(
        prompt,
        model,
        optimized,
        reference_hash,
        description_key=description_key,
        use_thinking=use_thinking,
        optimize_format=optimize_format,
    )
    elapsed = time.time() - start_time
    logger.info("Optimized in %.1fs model=%s", elapsed, model)
    if log_prompts():
        truncated = (
            optimized if len(optimized) <= _PROMPT_LOG_MAX else optimized[:_PROMPT_LOG_MAX] + "..."
        )
        logger.info("Optimized prompt: %s", truncated)
    return optimized


def _post_process_ollama_response(raw: str, optimize_format: str) -> str:
    """
    Post-process the raw Ollama response based on optimize_format.

    For "prose": strip thinking blocks and ANSI sequences, return cleaned text.
    For "json": strip thinking blocks, parse JSON, assemble to prose via _assemble_ideogram_json.
               Falls back to raw stripped text with a warning if JSON parsing fails.
    """
    cleaned = _strip_ollama_thinking(raw.strip())
    if optimize_format != "json":
        return cleaned

    # JSON path: attempt parse and assembly
    try:
        data = json.loads(cleaned)
        assembled = _assemble_ideogram_json(data)
        if assembled:
            return assembled
        logger.warning("JSON optimization produced empty assembly; falling back to raw text")
        return cleaned
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning(
            "JSON optimization response could not be parsed (%s); falling back to raw text",
            exc,
        )
        return cleaned


def _call_ollama_generate_api(
    config: Config,
    model: str,
    optimization_prompt: str,
    timeout: int,
    use_thinking: bool,
    optimize_format: str = "prose",
) -> str:
    """
    POST ``/api/generate`` with ``stream: false``; return the ``response`` text field.

    When optimize_format is "json", adds ``format: "json"`` to enforce structured output
    at the API level.

    Raises:
        RequestTimeoutError: HTTP timeout
        APIError: connection failure, HTTP error, or invalid JSON
    """
    base = _ollama_api_base(config)
    url = f"{base}/api/generate"
    payload: dict = {
        "model": model,
        "prompt": optimization_prompt,
        "stream": False,
        "think": use_thinking,
    }
    if optimize_format == "json":
        payload["format"] = "json"
    try:
        response = requests.post(
            url,
            json=payload,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
    except requests.exceptions.Timeout as err:
        raise RequestTimeoutError(
            f"Optimization timed out after {timeout} seconds. "
            "Try a simpler prompt or increase the timeout."
        ) from err
    except requests.exceptions.ConnectionError as err:
        raise APIError(
            "Failed to connect to Ollama. Is it running? Check OLLAMA_BASE_URL "
            f"or GENIMG_OLLAMA_BASE_URL (default {DEFAULT_OLLAMA_BASE_URL})."
        ) from err
    except requests.exceptions.RequestException as err:
        raise APIError(f"Ollama request failed: {err!s}") from err

    if response.status_code >= 400:
        raise APIError(
            f"Ollama optimization failed: {response.text}",
            status_code=response.status_code,
            response=response.text,
        )

    try:
        data = response.json()
    except ValueError as err:
        raise APIError(
            f"Ollama returned invalid JSON: {response.text[:500]}",
            response=response.text,
        ) from err

    text = data.get("response")
    if text is None:
        raise APIError("Ollama returned no response field", response=str(data)[:500])
    if not isinstance(text, str):
        raise APIError("Ollama response field has unexpected type", response=str(data)[:500])
    return text


def optimize_prompt(
    prompt: str,
    model: str | None = None,
    reference_hash: str | None = None,
    reference_description: str | None = None,
    enable_cache: bool = True,
    config: Config | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> str:
    """
    Optimize a prompt (main entry point).

    Args:
        prompt: The original prompt to optimize
        model: The optimization model to use (defaults to config)
        reference_hash: Hash of reference image if present
        reference_description: When set, use description-based template (REQ-014)
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
    description_key = reference_hash if reference_description else None
    if enable_cache:
        cache = get_cache()
        if model is None:
            model = config.default_optimization_model
        cached = cache.get(
            prompt,
            model,
            reference_hash,
            description_key=description_key,
            optimize_format=config.optimize_format,
        )
        if cached:
            logger.debug("Cache hit for model=%s", model)
            logger.info("Optimized (from cache) model=%s", model)
            return cached

    # Perform optimization (force_refresh when caller disabled cache for this request)
    return optimize_prompt_with_ollama(
        prompt,
        model,
        reference_hash,
        reference_description=reference_description,
        config=config,
        cancel_check=cancel_check,
        force_refresh=not enable_cache,
    )
