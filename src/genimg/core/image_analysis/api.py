"""
Image analysis facade and public entry points.

Singleton facade holds Florence and JoyTag backends; describe_image dispatches
by method (prose/tags). Optional get_description() with cache keyed by
(image_hash, method, options).
"""

from __future__ import annotations

import threading
from pathlib import Path

from PIL import Image

from genimg.core.image_analysis.backends.florence import (
    CAPTION_TASK_PROMPTS,
    FlorenceBackend,
)
from genimg.core.image_analysis.backends.joytag import JoyTagBackend
from genimg.core.image_analysis.image_utils import normalize_image_to_rgb_pil

# Module-level singleton backends; access under _lock
_lock = threading.Lock()
_florence: FlorenceBackend | None = None
_joytag: JoyTagBackend | None = None

# In-memory description cache: (image_hash, method, options_key) -> description
_description_cache: dict[tuple[str, str, str], str] = {}


def _get_florence() -> FlorenceBackend:
    global _florence
    with _lock:
        if _florence is None:
            _florence = FlorenceBackend()
        return _florence


def _get_joytag() -> JoyTagBackend:
    """Return or create JoyTag backend."""
    global _joytag
    with _lock:
        if _joytag is None:
            _joytag = JoyTagBackend()
        return _joytag


def _cache_key_options(method: str, verbosity: str, tag_threshold: float) -> str:
    """Stable string for cache key (method + options)."""
    if method == "prose":
        return f"prose:{verbosity}"
    return f"tags:{tag_threshold:.2f}"


def describe_image(
    image: Image.Image | str | Path | bytes,
    method: str = "prose",
    *,
    verbosity: str = "detailed",
    tag_threshold: float = 0.4,
) -> str:
    """
    Describe an image as tags (JoyTag) or prose (Florence-2).

    Image can be PIL Image, path (str or Path), or bytes. Normalized to RGB PIL
    internally. Raises ValidationError/ImageProcessingError for invalid input,
    RuntimeError on model load or inference failure.
    """
    pil = normalize_image_to_rgb_pil(image)
    if method == "prose":
        task_prompt = CAPTION_TASK_PROMPTS.get(verbosity, CAPTION_TASK_PROMPTS["detailed"])
        backend = _get_florence()
        try:
            return backend.caption(pil, task_prompt)
        except Exception as e:
            raise RuntimeError(f"Florence-2 describe failed: {e}") from e
    if method == "tags":
        joytag = _get_joytag()
        try:
            tags_list = joytag.predict_tags(pil, tag_threshold)
            return ", ".join(t[0] for t in tags_list)
        except Exception as e:
            raise RuntimeError(f"JoyTag describe failed: {e}") from e
    raise ValueError(f"Unknown method: {method!r}; use 'prose' or 'tags'")


def unload_describe_models() -> None:
    """
    Unload describe models from memory. Idempotent.
    Call before Ollama optimization/generation to free VRAM.
    """
    global _florence, _joytag
    with _lock:
        if _florence is not None:
            if _florence.is_loaded():
                _florence.unload()
            _florence = None
        if _joytag is not None:
            if _joytag.is_loaded():
                _joytag.unload()
            _joytag = None


def get_description(
    image: Image.Image | str | Path | bytes,
    image_hash: str | None,
    method: str,
    *,
    verbosity: str = "detailed",
    tag_threshold: float = 0.4,
) -> str:
    """
    Return description, from cache if possible.

    If image_hash is provided and cache has an entry for (image_hash, method,
    options), returns cached string. Otherwise normalizes image, calls
    describe_image, stores in cache, and returns.
    """
    options_key = _cache_key_options(method, verbosity, tag_threshold)
    if image_hash is not None:
        key = (image_hash, method, options_key)
        if key in _description_cache:
            return _description_cache[key]
    desc = describe_image(image, method=method, verbosity=verbosity, tag_threshold=tag_threshold)
    if image_hash is not None:
        _description_cache[(image_hash, method, options_key)] = desc
    return desc
