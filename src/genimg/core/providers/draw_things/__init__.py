"""
Draw Things gRPC client stack for core image generation.

Public entry points:

* :class:`DrawThingsClient`
* :class:`DrawThingsProvider`
* :func:`catalog.decode_metadata_override`
* Types: :class:`types.ZooCatalog`, model/LoRA info dataclasses
"""

from genimg.core.providers.draw_things.catalog import decode_metadata_override
from genimg.core.providers.draw_things.client import DrawThingsClient
from genimg.core.providers.draw_things.provider import DrawThingsProvider
from genimg.core.providers.draw_things.types import (
    ControlNetInfo,
    LoraInfo,
    ModelInfo,
    TextualInversionInfo,
    UpscalerInfo,
    ZooCatalog,
)

__all__ = [
    "ControlNetInfo",
    "DrawThingsClient",
    "DrawThingsProvider",
    "LoraInfo",
    "ModelInfo",
    "TextualInversionInfo",
    "UpscalerInfo",
    "ZooCatalog",
    "decode_metadata_override",
]
