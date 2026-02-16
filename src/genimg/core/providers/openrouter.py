"""
OpenRouter image generation provider.

Handles HTTP communication with the OpenRouter API for image generation
with optional reference images.
"""

import base64
import io
import json
import threading
import time
from collections.abc import Callable
from typing import Any

import requests
from PIL import Image

from genimg.core.config import Config
from genimg.core.image_gen import GenerationResult
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

_PROMPT_LOG_MAX = 50_000
_DEBUG_TRUNCATE_THRESHOLD = 200
_DEBUG_NEVER_TRUNCATE_KEYS = frozenset({"text", "message", "raw"})


def _truncate_image_data_for_log(obj: Any, parent_key: str | None = None) -> Any:
    """Recursively replace long base64/data URL strings with placeholders for safe logging."""
    if isinstance(obj, dict):
        return {k: _truncate_image_data_for_log(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate_image_data_for_log(v, None) for v in obj]
    if isinstance(obj, str) and len(obj) >= _DEBUG_TRUNCATE_THRESHOLD:
        if parent_key in _DEBUG_NEVER_TRUNCATE_KEYS:
            return obj
        if obj.startswith("data:"):
            return f"<data URL, {len(obj)} chars>"
        return f"<string, {len(obj)} chars>"
    return obj


def _format_from_content_type(content_type: str) -> str:
    """Infer image format from Content-Type header (e.g. 'image/jpeg' -> 'jpeg')."""
    if not content_type or not content_type.strip().lower().startswith("image/"):
        return "png"
    return content_type.split("/", 1)[1].lower().split(";")[0].strip() or "png"


class OpenRouterProvider:
    """Image generation provider for the OpenRouter API."""

    supports_reference_image: bool = True

    def _validate_config(self, config: Config, api_key_override: str | None) -> None:
        """Raise ValidationError if API key is missing."""
        api_key = api_key_override if api_key_override is not None else config.openrouter_api_key
        if not api_key:
            raise ValidationError(
                "OpenRouter API key is required. Set it via config or environment variable.",
                field="api_key",
            )

    def _build_payload(
        self,
        prompt: str,
        model: str,
        reference_image_b64: str | None,
    ) -> dict[str, Any]:
        """Build OpenRouter chat/completions payload."""
        content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if reference_image_b64:
            image_url = create_image_data_url(reference_image_b64)
            content_parts.append({"type": "image_url", "image_url": {"url": image_url}})
        return {
            "model": model,
            "modalities": ["image"],
            "messages": [{"role": "user", "content": content_parts}],
        }

    def _parse_response(
        self,
        response: requests.Response,
        model: str,
        prompt: str,
        had_ref: bool,
    ) -> GenerationResult:
        """Parse OpenRouter response into GenerationResult. Raises APIError on failure."""
        generation_time = time.time()  # caller sets start_time; we don't have it here
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
                had_reference=had_ref,
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
                had_reference=had_ref,
            )
        except (KeyError, IndexError, ValueError) as e:
            raise APIError(
                f"Failed to extract image from API response: {str(e)}",
                response=str(result),
            ) from e

    def _do_request(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: int,
        model: str,
        prompt: str,
        reference_image_b64: str | None,
        debug: bool,
    ) -> GenerationResult:
        """Perform HTTP POST and parse response. Maps status codes to exceptions."""
        logger.debug("API request url=%s model=%s timeout=%s", url, model, timeout)
        if debug:
            truncated = _truncate_image_data_for_log(payload)
            logger.info(
                "API request payload (image data truncated): %s",
                json.dumps(truncated, indent=2, default=str),
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
        if debug:
            content_type = response.headers.get("content-type", "")
            if content_type.startswith("image/"):
                logger.info(
                    "API response (image data truncated): <image body, %s bytes>",
                    len(response.content),
                )
            else:
                try:
                    result = response.json()
                    truncated = _truncate_image_data_for_log(result)
                    logger.info(
                        "API response (image data truncated): %s",
                        json.dumps(truncated, indent=2, default=str),
                    )
                except ValueError:
                    text = response.text
                    if len(text) > 2000:
                        text = text[:2000] + f"... <truncated, {len(response.text)} chars total>"
                    logger.info("API response (raw text): %s", text)

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

        result = self._parse_response(response, model, prompt, reference_image_b64 is not None)
        # Replace generation_time with actual measured time
        return GenerationResult(
            image=result.image,
            _format=result._format,
            generation_time=generation_time,
            model_used=result.model_used,
            prompt_used=result.prompt_used,
            had_reference=result.had_reference,
        )

    def generate(
        self,
        prompt: str,
        model: str,
        reference_image_b64: str | None,
        timeout: int,
        config: Config,
        cancel_check: Callable[[], bool] | None,
        *,
        api_key_override: str | None = None,
    ) -> GenerationResult:
        """Generate an image via OpenRouter API."""
        self._validate_config(config, api_key_override)
        api_key = api_key_override if api_key_override is not None else config.openrouter_api_key
        debug_api = getattr(config, "debug_api", False)

        url = f"{config.openrouter_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(prompt, model, reference_image_b64)

        has_ref = reference_image_b64 is not None
        logger.info("Generating image model=%s has_reference=%s", model, has_ref)
        if log_prompts():
            truncated = (
                prompt if len(prompt) <= _PROMPT_LOG_MAX else prompt[:_PROMPT_LOG_MAX] + "..."
            )
            logger.info("Prompt (used): %s", truncated)

        if cancel_check is None:
            try:
                result = self._do_request(
                    url, headers, payload, timeout, model, prompt, reference_image_b64, debug_api
                )
                logger.info(
                    "Generated in %.1fs model=%s", result.generation_time, result.model_used
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

        result_holder: list[GenerationResult | None] = [None]
        exc_holder: list[BaseException | None] = [None]

        def worker() -> None:
            try:
                result_holder[0] = self._do_request(
                    url, headers, payload, timeout, model, prompt, reference_image_b64, debug_api
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
                pass

        if exc_holder[0] is not None:
            raise exc_holder[0]
        assert result_holder[0] is not None
        result = result_holder[0]
        logger.info("Generated in %.1fs model=%s", result.generation_time, result.model_used)
        return result
