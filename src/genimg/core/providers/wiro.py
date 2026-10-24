"""Wiro.ai image generation provider."""

from __future__ import annotations

import io
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import requests
from PIL import Image

from genimg.core.config import (
    WIRO_POLL_INITIAL_INTERVAL_S,
    WIRO_POLL_MAX_INTERVAL_S,
    Config,
)
from genimg.core.image_gen import GenerationResult
from genimg.core.providers.wiro_client import (
    WIRO_SUCCESS_PEXIT,
    WIRO_TASK_DONE_STATUS,
    WiroClient,
    WiroTask,
)
from genimg.core.providers.wiro_schema import (
    build_run_plan,
    detect_image_format,
    parse_model_slugs,
)
from genimg.logging_config import get_logger
from genimg.utils.exceptions import (
    APIError,
    CancellationError,
    NetworkError,
    RequestTimeoutError,
    ValidationError,
)

logger = get_logger(__name__)

_schema_cache: dict[str, dict[str, Any]] = {}


def _format_from_content_type(content_type: str) -> str:
    if not content_type or not content_type.strip().lower().startswith("image/"):
        return "png"
    fmt = content_type.split("/", 1)[1].lower().split(";")[0].strip() or "png"
    return "jpeg" if fmt == "jpg" else fmt


class WiroProvider:
    """Image generation provider for the Wiro AI API."""

    supports_reference_image: bool = True

    def _validate_config(self, config: Config) -> None:
        if not (config.wiro_api_key or "").strip():
            raise ValidationError(
                "Wiro API key is required. Set WIRO_API_KEY environment variable.",
                field="api_key",
            )

    def _client(self, config: Config, request_timeout: int) -> WiroClient:
        return WiroClient(
            base_url=config.wiro_base_url,
            api_key=config.wiro_api_key,
            api_secret=config.wiro_api_secret or None,
            timeout=request_timeout,
        )

    def _cached_schema(self, client: WiroClient, owner: str, project: str) -> dict[str, Any]:
        cache_key = f"{owner}/{project}"
        if cache_key not in _schema_cache:
            _schema_cache[cache_key] = client.get_model_detail(owner, project)
        return _schema_cache[cache_key]

    def _pick_output_url(self, outputs: tuple[dict[str, Any], ...]) -> tuple[str, str]:
        for item in outputs:
            content_type = str(item.get("contenttype") or "")
            url = item.get("url")
            if isinstance(url, str) and url.strip() and content_type.lower().startswith("image/"):
                return url.strip(), content_type
        for item in outputs:
            url = item.get("url")
            if isinstance(url, str) and url.strip():
                content_type = str(item.get("contenttype") or "image/png")
                return url.strip(), content_type
        raise APIError(
            "No image output in Wiro task response.",
            response=str(outputs),
        )

    def _cancel_task(self, client: WiroClient, tasktoken: str) -> None:
        try:
            client.kill_task(tasktoken)
        except APIError:
            try:
                client.cancel_task(tasktoken)
            except APIError as e:
                logger.debug("Wiro task cancel/kill failed: %s", e)

    def _poll_until_done(
        self,
        client: WiroClient,
        tasktoken: str,
        *,
        deadline: float,
        cancel_check: Callable[[], bool] | None,
    ) -> WiroTask:
        interval = float(WIRO_POLL_INITIAL_INTERVAL_S)
        task: WiroTask | None = None
        while time.time() < deadline:
            if cancel_check is not None and cancel_check():
                self._cancel_task(client, tasktoken)
                raise CancellationError("Image generation was cancelled.")

            task = client.get_task(tasktoken=tasktoken)
            if task is not None and task.status == WIRO_TASK_DONE_STATUS:
                return task

            time.sleep(interval)
            interval = min(interval * 1.5, float(WIRO_POLL_MAX_INTERVAL_S))

        raise RequestTimeoutError("Wiro task did not complete before the timeout expired.")

    def _generate_impl(
        self,
        prompt: str,
        model: str,
        reference_images_b64: list[str] | None,
        timeout: int,
        config: Config,
        cancel_check: Callable[[], bool] | None,
        *,
        aspect_ratio: str | None = None,
        max_extent: int | None = None,
    ) -> GenerationResult:
        self._validate_config(config)
        owner, project = parse_model_slugs(model)
        client = self._client(config, request_timeout=min(timeout, 60))
        had_ref = bool(reference_images_b64)

        logger.info("Generating image via Wiro model=%s has_reference=%s", model, had_ref)
        start_time = time.time()
        deadline = start_time + timeout

        schema = self._cached_schema(client, owner, project)
        plan = build_run_plan(
            schema,
            prompt=prompt,
            reference_images_b64=reference_images_b64,
            model_label=model,
            aspect_ratio=aspect_ratio,
            max_extent=max_extent,
        )
        run = client.run_model(owner, project, plan)
        task = self._poll_until_done(
            client,
            run.socketaccesstoken,
            deadline=deadline,
            cancel_check=cancel_check,
        )

        if task.pexit != WIRO_SUCCESS_PEXIT:
            raise APIError(
                f"Wiro task failed with exit code {task.pexit!r}.",
                response=str(task.outputs),
            )

        output_url, content_type = self._pick_output_url(task.outputs)
        image_bytes = client.download_url(output_url)
        fmt = _format_from_content_type(content_type)
        try:
            pil_image = Image.open(io.BytesIO(image_bytes)).copy()
        except OSError as e:
            raise APIError(
                f"Failed to decode Wiro output image: {e}",
                response=output_url,
            ) from e

        generation_time = time.time() - start_time
        logger.info("Generated in %.1fs model=%s", generation_time, model)
        return GenerationResult(
            image=pil_image,
            _format=fmt if fmt != "png" else detect_image_format(image_bytes),
            generation_time=generation_time,
            model_used=model,
            prompt_used=prompt,
            had_reference=had_ref,
        )

    def generate(
        self,
        prompt: str,
        model: str,
        reference_images_b64: list[str] | None,
        timeout: int,
        config: Config,
        cancel_check: Callable[[], bool] | None,
        *,
        api_key_override: str | None = None,
        aspect_ratio: str | None = None,
        max_extent: int | None = None,
    ) -> GenerationResult:
        """Generate an image via Wiro API."""
        effective_config = config
        if api_key_override is not None:
            effective_config = replace(config, wiro_api_key=api_key_override)

        if cancel_check is None:
            try:
                return self._generate_impl(
                    prompt,
                    model,
                    reference_images_b64,
                    timeout,
                    effective_config,
                    None,
                    aspect_ratio=aspect_ratio,
                    max_extent=max_extent,
                )
            except requests.exceptions.Timeout as e:
                raise RequestTimeoutError(
                    f"Request timed out after {timeout} seconds. "
                    "The generation may be taking longer than expected."
                ) from e
            except requests.exceptions.ConnectionError as e:
                raise NetworkError(
                    "Failed to connect to Wiro API. Check your network connection.",
                    original_error=e,
                ) from e
            except requests.exceptions.RequestException as e:
                raise NetworkError(
                    f"Network error during Wiro request: {e}",
                    original_error=e,
                ) from e

        result_holder: list[GenerationResult | None] = [None]
        exc_holder: list[BaseException | None] = [None]

        def worker() -> None:
            try:
                result_holder[0] = self._generate_impl(
                    prompt,
                    model,
                    reference_images_b64,
                    timeout,
                    effective_config,
                    cancel_check,
                    aspect_ratio=aspect_ratio,
                    max_extent=max_extent,
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
                    "Failed to connect to Wiro API. Check your network connection.",
                    original_error=e,
                )
            except requests.exceptions.RequestException as e:
                exc_holder[0] = NetworkError(
                    f"Network error during Wiro request: {e}",
                    original_error=e,
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

        if exc_holder[0] is not None:
            raise exc_holder[0]
        assert result_holder[0] is not None
        return result_holder[0]


def load_cached_model_schema(config: Config, model: str) -> dict[str, Any]:
    """Load one Tool/Detail schema through the process-wide Wiro cache."""
    owner, project = parse_model_slugs(model)
    provider = WiroProvider()
    client = provider._client(config, request_timeout=min(config.generation_timeout, 60))
    return provider._cached_schema(client, owner, project)
