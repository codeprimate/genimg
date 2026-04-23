"""PoC :class:`ImageGenerationProvider`-shaped adapter (not registered in the global registry)."""

from __future__ import annotations

import base64
import io
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image

from genimg.contrib.draw_things_poc.client import DrawThingsClient
from genimg.contrib.draw_things_poc.constants import (
    DEFAULT_DRAW_THINGS_HOST,
    DEFAULT_DRAW_THINGS_PORT,
    ERR_PREFIX_API,
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

    supports_reference_image: bool = True

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
        refs = [r for r in (reference_images_b64 or []) if r and str(r).strip()]
        init_image: Image.Image | None = None
        if refs:
            if len(refs) > 1:
                logger.debug("Draw Things PoC: using first of %d reference images", len(refs))
            try:
                bin_img = base64.b64decode(refs[0].strip(), validate=False)
            except Exception as e:
                raise APIError(
                    f"{ERR_PREFIX_API} Invalid base64 in reference_images_b64[0].",
                    response=str(e),
                ) from e
            try:
                init_image = Image.open(io.BytesIO(bin_img)).copy()
            except Exception as e:
                raise APIError(
                    f"{ERR_PREFIX_API} reference_images_b64[0] is not a loadable image.",
                    response=str(e),
                ) from e

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
                init_image=init_image,
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
            had_reference=init_image is not None,
        )
