"""PoC :class:`ImageGenerationProvider`-shaped adapter (not registered in the global registry)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from genimg.contrib.draw_things_poc.client import DrawThingsClient
from genimg.contrib.draw_things_poc.constants import (
    DEFAULT_DRAW_THINGS_HOST,
    DEFAULT_DRAW_THINGS_PORT,
    MSG_PROVIDER_DECODE_NOT_IMPLEMENTED,
)
from genimg.contrib.draw_things_poc.generated import imageService_pb2_grpc as pb2_grpc
from genimg.contrib.draw_things_poc.tensor_image import dt_tensor_bytes_to_pil
from genimg.core.config import Config
from genimg.core.image_gen import GenerationResult
from genimg.logging_config import get_logger
from genimg.utils.exceptions import APIError

logger = get_logger(__name__)


class DrawThingsPoCProvider:
    """Image generation via local Draw Things gRPC (PoC; connection via constructor)."""

    supports_reference_image: bool = False

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        root_ca_pem_path: Path | None = None,
        use_tls: bool = True,
        insecure: bool = False,
        shared_secret: str | None = None,
        width_px: int = 512,
        height_px: int = 512,
        steps: int = 20,
        guidance_scale: float = 7.0,
        grpc_stub: pb2_grpc.ImageGenerationServiceStub | None = None,
    ) -> None:
        self._width_px = width_px
        self._height_px = height_px
        self._steps = steps
        self._guidance_scale = guidance_scale
        self._client = DrawThingsClient(
            host=host or DEFAULT_DRAW_THINGS_HOST,
            port=port if port is not None else DEFAULT_DRAW_THINGS_PORT,
            root_ca_pem_path=root_ca_pem_path,
            use_tls=use_tls,
            insecure=insecure,
            shared_secret=shared_secret,
            grpc_stub=grpc_stub,
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
    ) -> GenerationResult:
        del config, api_key_override
        if reference_images_b64:
            raise APIError("Draw Things PoC does not support reference images yet.", response="")

        start = time.time()
        with self._client:
            raw = self._client.generate_image_last_tensor(
                prompt=prompt,
                model=model,
                width_px=self._width_px,
                height_px=self._height_px,
                steps=self._steps,
                guidance_scale=self._guidance_scale,
                seed=None,
                timeout_seconds=float(timeout),
                cancel_check=cancel_check,
            )
        try:
            pil = dt_tensor_bytes_to_pil(raw)
        except Exception as e:
            logger.exception("Draw Things tensor decode failed")
            raise APIError(MSG_PROVIDER_DECODE_NOT_IMPLEMENTED, response=str(e)) from e

        elapsed = time.time() - start
        return GenerationResult(
            image=pil,
            _format="png",
            generation_time=elapsed,
            model_used=model,
            prompt_used=prompt,
            had_reference=False,
        )
