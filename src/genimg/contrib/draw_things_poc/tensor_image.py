"""Decode Draw Things ``generatedImages`` tensor bytes to a PIL image."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from genimg.contrib.draw_things_poc.constants import (
    DRAW_THINGS_TENSOR_COMPRESSED_MAGIC,
    MSG_DECODE_FAILED,
    MSG_FPZIP_DECOMPRESS_FAILED,
    MSG_FPZIP_IMPORT,
    TENSOR_HEADER_BYTE_LEN,
)
from genimg.utils.exceptions import APIError


def _float_tensor_to_u8_hwc(arr: np.ndarray) -> np.ndarray:
    """Normalize float RGB/RGBA in ~[-1, 1] to uint8 ``(H, W, C)``."""
    a = np.asarray(arr, dtype=np.float64)
    if a.ndim == 4 and a.shape[0] == 1:
        a = a[0]
    if a.ndim != 3:
        raise APIError(MSG_DECODE_FAILED, response=f"expected HWC float tensor, got shape {arr.shape}")
    return np.clip((a + 1.0) * 127.0, 0.0, 255.0).astype(np.uint8)


def _u8_hwc_to_pil(arr: np.ndarray) -> Image.Image:
    channels = int(arr.shape[2])
    if channels == 1:
        return Image.fromarray(arr[:, :, 0], mode="L").convert("RGB")
    if channels == 2:
        return Image.fromarray(arr, mode="LA").convert("RGB")
    if channels == 3:
        return Image.fromarray(arr, mode="RGB")
    if channels == 4:
        return Image.fromarray(arr[:, :, :3], mode="RGB")
    raise APIError(MSG_DECODE_FAILED, response=f"unsupported channel count {channels}")


def dt_tensor_bytes_to_pil(data: bytes) -> Image.Image:
    """Decode Draw Things tensor payload (float16 or fpzip-compressed float32 after header)."""
    if len(data) < TENSOR_HEADER_BYTE_LEN:
        raise APIError(MSG_DECODE_FAILED, response=f"too short: {len(data)} bytes")

    hdr = np.frombuffer(data[:TENSOR_HEADER_BYTE_LEN], dtype="<u4")
    magic = int(hdr[0])
    height = int(hdr[6])
    width = int(hdr[7])
    channels = int(hdr[8])

    if magic == DRAW_THINGS_TENSOR_COMPRESSED_MAGIC:
        try:
            import fpzip  # type: ignore[import-untyped]
        except ImportError as e:
            raise APIError(MSG_FPZIP_IMPORT, response=str(e)) from e
        comp = bytes(memoryview(data)[TENSOR_HEADER_BYTE_LEN:])
        try:
            f32 = fpzip.decompress(comp)
        except Exception as e:
            raise APIError(MSG_FPZIP_DECOMPRESS_FAILED, response=str(e)) from e
        u8 = _float_tensor_to_u8_hwc(np.asarray(f32))
        return _u8_hwc_to_pil(u8).copy()

    if height <= 0 or width <= 0 or channels <= 0:
        raise APIError(MSG_DECODE_FAILED, response=f"invalid dims {width}x{height}x{channels}")

    byte_len = width * height * channels * 2
    end = TENSOR_HEADER_BYTE_LEN + byte_len
    if len(data) < end:
        raise APIError(
            MSG_DECODE_FAILED,
            response=f"need {end} bytes, got {len(data)}",
        )

    f16 = np.frombuffer(
        memoryview(data)[TENSOR_HEADER_BYTE_LEN:end],
        dtype="<f2",
        count=width * height * channels,
    )
    u8 = np.clip((f16.astype(np.float64) + 1.0) * 127.0, 0.0, 255.0).astype(np.uint8)
    arr = u8.reshape((height, width, channels))
    return _u8_hwc_to_pil(arr).copy()


def dt_tensor_bytes_to_png_bytes(data: bytes) -> bytes:
    """Encode decoded tensor as PNG bytes."""
    img = dt_tensor_bytes_to_pil(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
