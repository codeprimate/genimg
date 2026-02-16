"""
Ollama image generation provider.

Uses Ollama's /api/generate endpoint for image-capable models (e.g. flux, llava).
Does not support reference images. Local deployment; no API key.
"""

import base64
import io
import threading
import time
from collections.abc import Callable

import requests
from PIL import Image

from genimg.core.config import DEFAULT_OLLAMA_BASE_URL, Config
from genimg.core.image_gen import GenerationResult
from genimg.logging_config import get_logger
from genimg.utils.exceptions import (
    APIError,
    CancellationError,
    NetworkError,
    RequestTimeoutError,
    ValidationError,
)

logger = get_logger(__name__)


def _format_from_content_type(content_type: str) -> str:
    """Infer image format from Content-Type header (e.g. 'image/jpeg' -> 'jpeg')."""
    if not content_type or not content_type.strip().lower().startswith("image/"):
        return "png"
    return content_type.split("/", 1)[1].lower().split(";")[0].strip() or "png"


class OllamaProvider:
    """Image generation provider for local Ollama (image-capable models)."""

    supports_reference_image: bool = False

    def _validate_config(self, config: Config) -> None:
        """Raise ValidationError if ollama_base_url is missing or invalid."""
        base_url = (config.ollama_base_url or "").strip()
        if not base_url:
            base_url = DEFAULT_OLLAMA_BASE_URL
        if not base_url:
            raise ValidationError(
                "Ollama base URL is required. Set OLLAMA_BASE_URL or GENIMG_OLLAMA_BASE_URL.",
                field="ollama_base_url",
            )

    def _parse_response(
        self,
        response: requests.Response,
        model: str,
        prompt: str,
        generation_time: float,
    ) -> GenerationResult:
        """Parse Ollama response into GenerationResult. Raises APIError on failure."""
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
                had_reference=False,
            )
        try:
            data = response.json()
        except ValueError as e:
            raise APIError(
                f"Failed to parse Ollama response as JSON: {str(e)}",
                response=response.text,
            ) from e
        # Spec §11: look for "image", "images"[0], or "response" as base64
        image_b64 = data.get("image")
        if not image_b64 and isinstance(data.get("images"), list) and data["images"]:
            image_b64 = data["images"][0]
        if not image_b64 and isinstance(data.get("response"), str):
            image_b64 = data["response"]
        if not image_b64:
            raise APIError(
                "No image in Ollama response. The model may not support image generation.",
                response=str(data),
            )
        try:
            image_data = base64.b64decode(image_b64)
        except ValueError as e:
            raise APIError(
                f"Invalid base64 image in Ollama response: {str(e)}",
                response=str(data),
            ) from e
        pil_image = Image.open(io.BytesIO(image_data)).copy()
        return GenerationResult(
            image=pil_image,
            _format="png",
            generation_time=generation_time,
            model_used=model,
            prompt_used=prompt,
            had_reference=False,
        )

    def _do_request(
        self,
        url: str,
        payload: dict,
        timeout: int,
        model: str,
        prompt: str,
    ) -> GenerationResult:
        """Perform HTTP POST and parse response. Maps status codes to exceptions."""
        logger.debug("Ollama request url=%s model=%s timeout=%s", url, model, timeout)
        start_time = time.time()
        response = requests.post(
            url,
            json=payload,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        generation_time = time.time() - start_time
        logger.debug(
            "Ollama response status=%s content_type=%s time=%.2fs",
            response.status_code,
            response.headers.get("content-type", ""),
            generation_time,
        )
        if response.status_code >= 400:
            raise APIError(
                f"Ollama API error: {response.status_code}",
                status_code=response.status_code,
                response=response.text,
            )
        if response.status_code != 200:
            raise APIError(
                f"Ollama request failed with status {response.status_code}: {response.text}",
                status_code=response.status_code,
                response=response.text,
            )
        return self._parse_response(response, model, prompt, generation_time)

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
        """Generate an image via Ollama. reference_image_b64 is ignored (not supported)."""
        self._validate_config(config)
        base_url = (
            config.ollama_base_url or DEFAULT_OLLAMA_BASE_URL
        ).strip() or DEFAULT_OLLAMA_BASE_URL
        url = f"{base_url.rstrip('/')}/api/generate"
        payload = {"model": model, "prompt": prompt, "stream": False}

        logger.info("Generating image via Ollama model=%s", model)

        if cancel_check is None:
            try:
                result = self._do_request(url, payload, timeout, model, prompt)
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
                    "Failed to connect to Ollama. Is it running? Check OLLAMA_BASE_URL.",
                    original_error=e,
                ) from e
            except requests.exceptions.RequestException as e:
                raise NetworkError(
                    f"Network error during Ollama request: {str(e)}", original_error=e
                ) from e

        result_holder: list[GenerationResult | None] = [None]
        exc_holder: list[BaseException | None] = [None]

        def worker() -> None:
            try:
                result_holder[0] = self._do_request(url, payload, timeout, model, prompt)
            except requests.exceptions.Timeout as e:
                err = RequestTimeoutError(
                    f"Request timed out after {timeout} seconds. "
                    "The generation may be taking longer than expected."
                )
                err.__cause__ = e
                exc_holder[0] = err
            except requests.exceptions.ConnectionError as e:
                exc_holder[0] = NetworkError(
                    "Failed to connect to Ollama. Is it running? Check OLLAMA_BASE_URL.",
                    original_error=e,
                )
            except requests.exceptions.RequestException as e:
                exc_holder[0] = NetworkError(
                    f"Network error during Ollama request: {str(e)}", original_error=e
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
