"""Draw Things :class:`ImageGenerationProvider` adapter for core integration."""

from __future__ import annotations

import base64
import io
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from genimg.core.providers.draw_things.client import DrawThingsClient
from genimg.core.providers.draw_things.constants import (
    DEFAULT_DRAW_THINGS_HOST,
    DEFAULT_DRAW_THINGS_PORT,
    DEFAULT_STRENGTH,
    ERR_PREFIX_API,
    MIN_GENERATION_TIMEOUT_SECONDS,
    MSG_PROVIDER_DECODE_NOT_IMPLEMENTED,
)
from genimg.core.providers.draw_things.generated import imageService_pb2_grpc as pb2_grpc
from genimg.core.providers.draw_things.presets import resolve_draw_things_preset
from genimg.core.providers.draw_things.tensor_image import dt_tensor_bytes_to_pil
from genimg.core.config import Config
from genimg.core.image_gen import GenerationResult
from genimg.logging_config import get_logger
from genimg.utils.exceptions import APIError, ValidationError

logger = get_logger(__name__)


@dataclass(slots=True)
class _ResolvedTuning:
    width_px: int
    height_px: int
    steps: int
    guidance_scale: float
    strength: float
    sampler: int | None
    hires_fix: bool
    upscaler: str | None
    upscaler_scale_factor: int | None


class DrawThingsProvider:
    """Image generation via local Draw Things gRPC."""

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
        self._host = host
        self._port = port
        self._root_ca_pem_path = root_ca_pem_path
        self._use_tls = use_tls
        self._insecure = insecure
        self._shared_secret = shared_secret
        self._grpc_stub = grpc_stub

    def _resolve_tuning(self, config: Config) -> _ResolvedTuning:
        preset_name = getattr(config, "draw_things_preset", None)
        preset = resolve_draw_things_preset(preset_name)
        if preset_name and preset is None:
            raise ValidationError(
                f"Unknown Draw Things preset: {preset_name!r}.",
                field="draw_things_preset",
            )

        if preset is not None:
            resolved = _ResolvedTuning(
                width_px=preset.width_px,
                height_px=preset.height_px,
                steps=preset.steps,
                guidance_scale=preset.guidance_scale,
                strength=preset.strength,
                sampler=int(preset.sampler),
                hires_fix=bool(preset.default_hires_fix),
                upscaler=preset.default_upscaler,
                upscaler_scale_factor=preset.default_upscaler_scale_factor,
            )
        else:
            resolved = _ResolvedTuning(
                width_px=self._width_px,
                height_px=self._height_px,
                steps=self._steps,
                guidance_scale=self._guidance_scale,
                strength=DEFAULT_STRENGTH,
                sampler=None,
                hires_fix=False,
                upscaler=None,
                upscaler_scale_factor=None,
            )

        overrides: tuple[tuple[str, str], ...] = (
            ("draw_things_width_px", "width_px"),
            ("draw_things_height_px", "height_px"),
            ("draw_things_steps", "steps"),
            ("draw_things_guidance_scale", "guidance_scale"),
            ("draw_things_strength", "strength"),
            ("draw_things_sampler", "sampler"),
            ("draw_things_hires_fix", "hires_fix"),
            ("draw_things_upscaler", "upscaler"),
            ("draw_things_upscaler_scale_factor", "upscaler_scale_factor"),
        )
        for config_field, target_field in overrides:
            value = getattr(config, config_field, None)
            if value is not None:
                setattr(resolved, target_field, value)

        return resolved

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
        del api_key_override
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
        host = getattr(config, "draw_things_host", None) or self._host or DEFAULT_DRAW_THINGS_HOST
        port = getattr(config, "draw_things_port", None)
        if port is None:
            port = self._port if self._port is not None else DEFAULT_DRAW_THINGS_PORT
        root_ca_pem_path = getattr(config, "draw_things_root_ca_pem_path", None) or self._root_ca_pem_path
        use_tls = getattr(config, "draw_things_use_tls", self._use_tls)
        insecure = getattr(config, "draw_things_insecure", self._insecure)
        shared_secret = getattr(config, "draw_things_shared_secret", None) or self._shared_secret
        tuning = self._resolve_tuning(config)

        # Create a short-lived client per request to preserve thread-safe behavior.
        with DrawThingsClient(
            host=host,
            port=port,
            root_ca_pem_path=root_ca_pem_path,
            use_tls=use_tls,
            insecure=insecure,
            shared_secret=shared_secret,
            grpc_stub=self._grpc_stub,
        ) as client:
            timeout_seconds = float(max(timeout, MIN_GENERATION_TIMEOUT_SECONDS))
            raw = client.generate_image_last_tensor(
                prompt=prompt,
                model=model,
                width_px=tuning.width_px,
                height_px=tuning.height_px,
                steps=tuning.steps,
                guidance_scale=tuning.guidance_scale,
                seed=None,
                timeout_seconds=timeout_seconds,
                cancel_check=cancel_check,
                strength=tuning.strength,
                sampler=tuning.sampler,
                hires_fix=tuning.hires_fix,
                upscaler=tuning.upscaler,
                upscaler_scale_factor=tuning.upscaler_scale_factor,
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
