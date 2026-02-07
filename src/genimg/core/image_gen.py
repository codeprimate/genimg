"""
Image generation via OpenRouter API.

This module handles communication with the OpenRouter API to generate images
from text prompts and optional reference images.
"""

import base64
import time
from dataclasses import dataclass
from typing import Optional

import requests

from genimg.core.config import Config, get_config
from genimg.core.reference import create_image_data_url
from genimg.utils.exceptions import APIError, NetworkError, RequestTimeoutError, ValidationError


def _format_from_content_type(content_type: str) -> str:
    """Infer image format from Content-Type header (e.g. 'image/jpeg' -> 'jpeg')."""
    if not content_type or not content_type.strip().lower().startswith("image/"):
        return "png"
    return content_type.split("/", 1)[1].lower().split(";")[0].strip() or "png"


@dataclass
class GenerationResult:
    """Result of an image generation operation."""

    image_data: bytes  # Raw image bytes
    format: str  # Image format, e.g. 'jpeg' or 'png'
    generation_time: float  # Time taken in seconds
    model_used: str  # Model that generated the image
    prompt_used: str  # Prompt that was used
    had_reference: bool  # Whether a reference image was used


def generate_image(
    prompt: str,
    model: Optional[str] = None,
    reference_image_b64: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[int] = None,
    config: Optional[Config] = None,
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

    Returns:
        GenerationResult with image data and metadata

    Raises:
        ValidationError: If inputs are invalid
        APIError: If API call fails
        NetworkError: If network error occurs
        RequestTimeoutError: If request times out
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

    # Prepare the API request
    url = f"{config.openrouter_base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Build the message content
    content_parts = [{"type": "text", "text": prompt}]

    # Add reference image if provided
    if reference_image_b64:
        image_url = create_image_data_url(reference_image_b64)
        content_parts.append({"type": "image_url", "image_url": {"url": image_url}})

    payload = {
        "model": model,
        "modalities": ["image"],
        "messages": [{"role": "user", "content": content_parts}],
    }

    # Make the API request
    start_time = time.time()

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)

        generation_time = time.time() - start_time

        # Handle HTTP errors
        if response.status_code == 401:
            raise APIError(
                "Authentication failed. Please check your OpenRouter API key.",
                status_code=401,
                response=response.text,
            )
        elif response.status_code == 404:
            raise APIError(
                f"Model not found or endpoint unavailable: {model}",
                status_code=404,
                response=response.text,
            )
        elif response.status_code == 429:
            raise APIError(
                "Rate limit exceeded. Please wait before making more requests.",
                status_code=429,
                response=response.text,
            )
        elif response.status_code >= 500:
            raise APIError(
                f"OpenRouter service error: {response.status_code}",
                status_code=response.status_code,
                response=response.text,
            )
        elif response.status_code != 200:
            raise APIError(
                f"API request failed with status {response.status_code}: {response.text}",
                status_code=response.status_code,
                response=response.text,
            )

        # Check if response is an image (direct image response)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("image/"):
            image_data = response.content
            fmt = _format_from_content_type(content_type)
            return GenerationResult(
                image_data=image_data,
                format=fmt,
                generation_time=generation_time,
                model_used=model,
                prompt_used=prompt,
                had_reference=reference_image_b64 is not None,
            )

        # Parse JSON response
        try:
            result = response.json()
        except ValueError as e:
            raise APIError(
                f"Failed to parse API response as JSON: {str(e)}",
                response=response.text,
            ) from e

        # Extract image from response
        try:
            # Check for images in the response
            images = result.get("choices", [{}])[0].get("message", {}).get("images", [])

            if not images:
                raise APIError(
                    "No images in API response. The model may not support image generation.",
                    response=str(result),
                )

            # Get the first image URL (should be base64 data URL)
            image_url = images[0].get("image_url", {}).get("url", "")

            if not image_url:
                raise APIError("No image URL in response", response=str(result))

            # Decode base64 image
            if image_url.startswith("data:"):
                # Extract base64 data from data URL
                base64_data = image_url.split(",", 1)[1]
                image_data = base64.b64decode(base64_data)
            else:
                # Assume it's already base64
                image_data = base64.b64decode(image_url)

            return GenerationResult(
                image_data=image_data,
                format="png",
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
        raise NetworkError(f"Network error during API request: {str(e)}", original_error=e) from e
