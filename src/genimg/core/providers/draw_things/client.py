"""gRPC client for Draw Things ``Echo`` and ``GenerateImage``."""

from __future__ import annotations

import hashlib
import socket
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import grpc  # type: ignore[import-untyped]
from PIL import Image

from genimg.core.providers.draw_things.catalog import decode_metadata_override, empty_zoo_catalog
from genimg.core.providers.draw_things.config_builder import (
    build_txt2img_configuration_bytes,
    round_dimension_to_multiple_of_64,
)
from genimg.core.providers.draw_things.constants import (
    DEFAULT_CHUNKED,
    DEFAULT_DRAW_THINGS_HOST,
    DEFAULT_DRAW_THINGS_PORT,
    DEFAULT_NEGATIVE_PROMPT,
    DEFAULT_STRENGTH,
    GRPC_MAX_RECEIVE_MESSAGE_LENGTH,
    GRPC_MAX_SEND_MESSAGE_LENGTH,
    SCALE_FACTOR_DEFAULT,
)
from genimg.core.providers.draw_things.generated import imageService_pb2_grpc as pb2_grpc
from genimg.core.providers.draw_things.generated.imageService_pb2 import (
    DeviceType,
    EchoReply,
    EchoRequest,
    ImageGenerationRequest,
    ImageGenerationResponse,
)
from genimg.core.providers.draw_things.generated.SamplerType import SamplerType
from genimg.core.providers.draw_things.tensor_image import (
    full_img2img_denoise_mask_bytes,
    pil_to_dt_tensor_bytes,
)
from genimg.core.providers.draw_things.types import (
    ControlNetInfo,
    LoraInfo,
    ModelInfo,
    TextualInversionInfo,
    UpscalerInfo,
    ZooCatalog,
)
from genimg.logging_config import get_logger
from genimg.utils.exceptions import APIError, CancellationError, NetworkError, RequestTimeoutError

logger = get_logger(__name__)


class _NoopGrpcChannel:
    """Minimal channel placeholder when a test injects ``grpc_stub``."""

    def close(self) -> None:
        return None


def _grpc_channel_options() -> tuple[tuple[str, int], ...]:
    return (
        ("grpc.max_send_message_length", GRPC_MAX_SEND_MESSAGE_LENGTH),
        ("grpc.max_receive_message_length", GRPC_MAX_RECEIVE_MESSAGE_LENGTH),
    )


class DrawThingsClient:
    """PoC client: TLS channel by default, Echo catalog, ``GenerateImage`` streaming."""

    def __init__(
        self,
        *,
        host: str = DEFAULT_DRAW_THINGS_HOST,
        port: int = DEFAULT_DRAW_THINGS_PORT,
        root_ca_pem_path: Path | None = None,
        use_tls: bool = True,
        insecure: bool = False,
        shared_secret: str | None = None,
        grpc_stub: pb2_grpc.ImageGenerationServiceStub | None = None,
    ) -> None:
        self._host = host
        self._port = int(port)
        self._root_ca_pem_path = root_ca_pem_path
        self._use_tls = use_tls and not insecure
        self._insecure = insecure
        self._shared_secret = shared_secret
        self._injected_stub = grpc_stub
        self._channel: grpc.Channel | _NoopGrpcChannel | None = None
        self._stub: pb2_grpc.ImageGenerationServiceStub | None = None
        self._request_id = 0
        self._catalog_cache: ZooCatalog | None = None

    def _target(self) -> str:
        return f"{self._host}:{self._port}"

    def _ensure_channel(self) -> grpc.Channel | _NoopGrpcChannel:
        if self._injected_stub is not None:
            if self._channel is None:
                self._channel = _NoopGrpcChannel()
            if self._stub is None:
                self._stub = self._injected_stub
            return self._channel

        if self._channel is not None:
            return self._channel
        opts = _grpc_channel_options()
        target = self._target()
        if self._insecure:
            self._channel = grpc.insecure_channel(target, options=list(opts))
        elif self._use_tls:
            ca_path = self._root_ca_pem_path
            if ca_path is None:
                from genimg.core.providers.draw_things.constants import default_root_ca_pem_path

                ca_path = default_root_ca_pem_path()
            pem = ca_path.read_bytes()
            creds = grpc.ssl_channel_credentials(root_certificates=pem)
            self._channel = grpc.secure_channel(target, creds, options=list(opts))
        else:
            self._channel = grpc.insecure_channel(target, options=list(opts))
        self._stub = pb2_grpc.ImageGenerationServiceStub(self._channel)
        return self._channel

    def close(self) -> None:
        if self._channel is not None:
            self._channel.close()
        self._channel = None
        self._stub = None

    def __enter__(self) -> DrawThingsClient:
        self._ensure_channel()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def echo_raw(self) -> EchoReply:
        self._ensure_channel()
        assert self._stub is not None
        req = EchoRequest(name="")
        if self._shared_secret:
            req.sharedSecret = self._shared_secret
        return self._stub.Echo(req)

    def fetch_zoo_catalog(self, *, use_cache: bool = True) -> ZooCatalog:
        """Call ``Echo`` and decode ``MetadataOverride`` into a :class:`ZooCatalog`."""
        if use_cache and self._catalog_cache is not None:
            return self._catalog_cache
        reply = self.echo_raw()
        if not reply.HasField("override"):
            catalog = empty_zoo_catalog()
        else:
            catalog = decode_metadata_override(reply.override)
        self._catalog_cache = catalog
        return catalog

    def clear_catalog_cache(self) -> None:
        self._catalog_cache = None

    def list_models(self) -> tuple[ModelInfo, ...]:
        return self.fetch_zoo_catalog().models

    def list_loras(self) -> tuple[LoraInfo, ...]:
        return self.fetch_zoo_catalog().loras

    def list_control_nets(self) -> tuple[ControlNetInfo, ...]:
        return self.fetch_zoo_catalog().control_nets

    def list_textual_inversions(self) -> tuple[TextualInversionInfo, ...]:
        return self.fetch_zoo_catalog().textual_inversions

    def list_upscalers(self) -> tuple[UpscalerInfo, ...]:
        return self.fetch_zoo_catalog().upscalers

    def generate_image_stream(
        self,
        *,
        prompt: str,
        negative_prompt: str | None,
        model: str,
        width_px: int,
        height_px: int,
        steps: int,
        guidance_scale: float,
        seed: int | None,
        timeout_seconds: float,
        cancel_check: Callable[[], bool] | None = None,
        loras: Sequence[tuple[str, float]] | None = None,
        hires_fix: bool = False,
        upscaler: str | None = None,
        upscaler_scale_factor: int | None = None,
        hires_fix_strength: float = 0.7,
        strength: float = DEFAULT_STRENGTH,
        sampler: int | None = None,
        init_image: Image.Image | None = None,
    ) -> Iterator[ImageGenerationResponse]:
        self._ensure_channel()
        assert self._stub is not None

        neg = DEFAULT_NEGATIVE_PROMPT if negative_prompt is None else negative_prompt
        use_sampler = SamplerType.DPMPP2MKarras if sampler is None else int(sampler)
        cfg_bytes = build_txt2img_configuration_bytes(
            model=model,
            width_px=width_px,
            height_px=height_px,
            steps=steps,
            guidance_scale=guidance_scale,
            seed=seed,
            request_id=self._next_request_id(),
            loras=loras,
            hires_fix=hires_fix,
            upscaler=upscaler,
            upscaler_scale_factor=upscaler_scale_factor,
            hires_fix_strength=hires_fix_strength,
            strength=strength,
            sampler=use_sampler,
            for_img2img=init_image is not None,
        )

        req = ImageGenerationRequest()
        req.prompt = prompt
        req.negativePrompt = neg
        req.configuration = cfg_bytes
        req.scaleFactor = SCALE_FACTOR_DEFAULT
        req.user = socket.gethostname()
        req.device = DeviceType.LAPTOP
        req.chunked = DEFAULT_CHUNKED
        if self._shared_secret:
            req.sharedSecret = self._shared_secret

        if init_image is not None:
            tensor = pil_to_dt_tensor_bytes(init_image, width_px, height_px)
            rh = round_dimension_to_multiple_of_64(height_px)
            rw = round_dimension_to_multiple_of_64(width_px)
            mask = full_img2img_denoise_mask_bytes(rh, rw)
            req.image = hashlib.sha256(tensor).digest()
            req.contents.append(tensor)
            req.mask = hashlib.sha256(mask).digest()
            req.contents.append(mask)

        deadline = time.monotonic() + timeout_seconds
        stream = self._stub.GenerateImage(req, timeout=timeout_seconds)
        for msg in stream:
            if cancel_check and cancel_check():
                stream.cancel()
                raise CancellationError("Draw Things generation was cancelled.")
            if time.monotonic() > deadline:
                stream.cancel()
                raise RequestTimeoutError("Draw Things generation exceeded deadline.")
            yield msg

    def generate_image_last_tensor(
        self,
        *,
        prompt: str,
        negative_prompt: str | None = None,
        model: str,
        width_px: int,
        height_px: int,
        steps: int,
        guidance_scale: float,
        seed: int | None,
        timeout_seconds: float,
        cancel_check: Callable[[], bool] | None = None,
        loras: Sequence[tuple[str, float]] | None = None,
        hires_fix: bool = False,
        upscaler: str | None = None,
        upscaler_scale_factor: int | None = None,
        hires_fix_strength: float = 0.7,
        strength: float = DEFAULT_STRENGTH,
        sampler: int | None = None,
        init_image: Image.Image | None = None,
    ) -> bytes:
        """Consume the stream and return the last non-empty ``generatedImages`` payload."""
        last: bytes | None = None
        try:
            for msg in self.generate_image_stream(
                prompt=prompt,
                negative_prompt=negative_prompt,
                model=model,
                width_px=width_px,
                height_px=height_px,
                steps=steps,
                guidance_scale=guidance_scale,
                seed=seed,
                timeout_seconds=timeout_seconds,
                cancel_check=cancel_check,
                loras=loras,
                hires_fix=hires_fix,
                upscaler=upscaler,
                upscaler_scale_factor=upscaler_scale_factor,
                hires_fix_strength=hires_fix_strength,
                strength=strength,
                sampler=sampler,
                init_image=init_image,
            ):
                if msg.generatedImages:
                    last = bytes(msg.generatedImages[-1])
        except grpc.RpcError as e:
            raise NetworkError(f"Draw Things gRPC error: {e.code().name}", original_error=e) from e
        if not last:
            raise APIError("Draw Things returned no image bytes.", response="")
        return last
