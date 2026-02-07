"""
Image generation via OpenRouter API.

This module handles communication with the OpenRouter API to generate images
from text prompts and optional reference images.
"""

import base64
import io
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests
from PIL import Image

from genimg.core.config import Config, get_config
from genimg.core.reference import create_image_data_url
from genimg.logging_config import get_logger, log_prompts
from genimg.utils.exceptions import (
    APIError,
    CancellationError,
    NetworkError,
    RequestTimeoutError,
    ValidationError,
)

logger = get_logger(__name__)

# Max prompt length for logging (large so prompts are effectively never truncated)
_PROMPT_LOG_MAX = 50_000


def _format_from_content_type(content_type: str) -> str:
    """Infer image format from Content-Type header (e.g. 'image/jpeg' -> 'jpeg')."""
    if not content_type or not content_type.strip().lower().startswith("image/"):
        return "png"
    return content_type.split("/", 1)[1].lower().split(";")[0].strip() or "png"


@dataclass
class GenerationResult:
    """Result of an image generation operation.

    The primary output is ``image`` (a PIL Image). Use it to save, convert format,
    or get bytes as needed. ``image_data`` and ``format`` are provided for
    backward compatibility.
    """

    image: Image.Image  # PIL Image; caller can save, convert, or get bytes as needed
    _format: str  # Format from API, e.g. 'jpeg' or 'png'
    generation_time: float  # Time taken in seconds
    model_used: str  # Model that generated the image
    prompt_used: str  # Prompt that was used
    had_reference: bool  # Whether a reference image was used

    @property
    def format(self) -> str:
        """Image format from the API (e.g. 'jpeg', 'png')."""
        return self._format

    @property
    def image_data(self) -> bytes:
        """Raw image bytes in the API's format (for backward compatibility)."""
        buf = io.BytesIO()
        self.image.save(buf, format=self._format)
        return buf.getvalue()


def _do_generate_image_request(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int,
    model: str,
    prompt: str,
    reference_image_b64: str | None,
) -> GenerationResult:
    """Perform the HTTP request and parse response; used by generate_image (and by worker when cancellable)."""
    logger.debug(
        "API request url=%s model=%s timeout=%s",
        url,
        model,
        timeout,
    )
    start_time = time.time()
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    generation_time = time.time() - start_time
    logger.debug(
        "API response status=%s content_type=%s time=%.2fs",
        response.status_code,
        response.headers.get("content-type", ""),
        generation_time,
    )

    if response.status_code == 401:
        raise APIError(
            "Authentication failed. Please check your OpenRouter API key.",
            status_code=401,
            response=response.text,
        )
    if response.status_code == 404:
        raise APIError(
            f"Model not found or endpoint unavailable: {model}",
            status_code=404,
            response=response.text,
        )
    if response.status_code == 429:
        raise APIError(
            "Rate limit exceeded. Please wait before making more requests.",
            status_code=429,
            response=response.text,
        )
    if response.status_code >= 500:
        raise APIError(
            f"OpenRouter service error: {response.status_code}",
            status_code=response.status_code,
            response=response.text,
        )
    if response.status_code != 200:
        raise APIError(
            f"API request failed with status {response.status_code}: {response.text}",
            status_code=response.status_code,
            response=response.text,
        )

    content_type = response.headers.get("content-type", "")
    if content_type.startswith("image/"):
        image_data = response.content
        fmt = _format_from_content_type(content_type)
        pil_image = Image.open(io.BytesIO(image_data)).copy()
        return GenerationResult(
            image=pil_image,
            _format=fmt,
            generation_time=generation_time,
            model_used=model,
            prompt_used=prompt,
            had_reference=reference_image_b64 is not None,
        )

    try:
        result = response.json()
    except ValueError as e:
        raise APIError(
            f"Failed to parse API response as JSON: {str(e)}",
            response=response.text,
        ) from e

    try:
        images = result.get("choices", [{}])[0].get("message", {}).get("images", [])
        if not images:
            raise APIError(
                "No images in API response. The model may not support image generation.",
                response=str(result),
            )
        image_url = images[0].get("image_url", {}).get("url", "")
        if not image_url:
            raise APIError("No image URL in response", response=str(result))
        if image_url.startswith("data:"):
            base64_data = image_url.split(",", 1)[1]
            image_data = base64.b64decode(base64_data)
        else:
            image_data = base64.b64decode(image_url)
        pil_image = Image.open(io.BytesIO(image_data)).copy()
        return GenerationResult(
            image=pil_image,
            _format="png",
            generation_time=generation_time,
            model_used=model,
            prompt_used=prompt,
            had_reference=reference_image_b64 is not None,
        )
    except (KeyError, IndexError, ValueError) as e:
        raise APIError(
            f"Failed to extract image from API response: {str(e)}",
            response=str(result),
        ) from e


def generate_image(
    prompt: str,
    model: str | None = None,
    reference_image_b64: str | None = None,
    api_key: str | None = None,
    timeout: int | None = None,
    config: Config | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> GenerationResult:
    """
    Generate an image using OpenRouter API.

    Args:
        prompt: Text prompt describing the desired image
        model: Model ID to use (defaults to config value)
        reference_image_b64: Optional base64-encoded reference image
        api_key: Optional API key (defaults to config value)
        timeout: Optional timeout in seconds (defaults to config value)
        config: Optional config to use; if None, uses shared config from get_config()
        cancel_check: Optional callable returning True to cancel; polled during the request.
            Should return quickly and not raise (exceptions are caught and ignored).

    Returns:
        GenerationResult with image data and metadata

    Raises:
        ValidationError: If inputs are invalid
        APIError: If API call fails
        NetworkError: If network error occurs
        RequestTimeoutError: If request times out
        CancellationError: If cancel_check returned True
    """
    if not prompt or not prompt.strip():
        raise ValidationError("Prompt cannot be empty", field="prompt")

    config = config or get_config()

    if model is None:
        model = config.default_image_model

    if api_key is None:
        api_key = config.openrouter_api_key
        if not api_key:
            raise ValidationError(
                "OpenRouter API key is required. Set it via config or environment variable.",
                field="api_key",
            )

    if timeout is None:
        timeout = config.generation_timeout

    has_ref = reference_image_b64 is not None
    logger.info(
        "Generating image model=%s has_reference=%s",
        model,
        has_ref,
    )
    if log_prompts():
        truncated = prompt if len(prompt) <= _PROMPT_LOG_MAX else prompt[:_PROMPT_LOG_MAX] + "..."
        logger.info("Prompt (used): %s", truncated)

    url = f"{config.openrouter_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    if reference_image_b64:
        image_url = create_image_data_url(reference_image_b64)
        content_parts.append({"type": "image_url", "image_url": {"url": image_url}})
    payload = {
        "model": model,
        "modalities": ["image"],
        "messages": [{"role": "user", "content": content_parts}],
    }

    if cancel_check is None:
        try:
            result = _do_generate_image_request(
                url, headers, payload, timeout, model, prompt, reference_image_b64
            )
            logger.info(
                "Generated in %.1fs model=%s",
                result.generation_time,
                result.model_used,
            )
            return result
        except requests.exceptions.Timeout as e:
            raise RequestTimeoutError(
                f"Request timed out after {timeout} seconds. "
                "The generation may be taking longer than expected."
            ) from e
        except requests.exceptions.ConnectionError as e:
            raise NetworkError(
                "Failed to connect to OpenRouter API. Please check your internet connection.",
                original_error=e,
            ) from e
        except requests.exceptions.RequestException as e:
            raise NetworkError(
                f"Network error during API request: {str(e)}", original_error=e
            ) from e

    # Run with cancellation support: request in a thread, main thread polls cancel_check
    result_holder: list[GenerationResult | None] = [None]
    exc_holder: list[BaseException | None] = [None]

    def worker() -> None:
        try:
            result_holder[0] = _do_generate_image_request(
                url, headers, payload, timeout, model, prompt, reference_image_b64
            )
        except requests.exceptions.Timeout as e:
            err = RequestTimeoutError(
                f"Request timed out after {timeout} seconds. "
                "The generation may be taking longer than expected."
            )
            err.__cause__ = e
            exc_holder[0] = err
        except requests.exceptions.ConnectionError as e:
            exc_holder[0] = NetworkError(
                "Failed to connect to OpenRouter API. Please check your internet connection.",
                original_error=e,
            )
        except requests.exceptions.RequestException as e:
            exc_holder[0] = NetworkError(
                f"Network error during API request: {str(e)}", original_error=e
            )
        except BaseException as e:
            exc_holder[0] = e

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    poll_interval = 0.25
    while True:
        thread.join(timeout=poll_interval)
        if not thread.is_alive():
            break
        try:
            if cancel_check():
                raise CancellationError("Image generation was cancelled.")
        except CancellationError:
            raise
        except Exception:
            pass  # Don't let a buggy cancel_check break the loop

    if exc_holder[0] is not None:
        raise exc_holder[0]
    assert result_holder[0] is not None
    result = result_holder[0]
    logger.info(
        "Generated in %.1fs model=%s",
        result.generation_time,
        result.model_used,
    )
    return result
