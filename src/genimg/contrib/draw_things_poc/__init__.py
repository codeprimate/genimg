"""
Draw Things gRPC PoC client (local image generation).

Install optional dependencies::

    pip install 'genimg[draw-things]'

Public entry points:

* :class:`DrawThingsClient`
* :class:`DrawThingsPoCProvider`
* :func:`catalog.decode_metadata_override`
* Types: :class:`types.ZooCatalog`, model/LoRA info dataclasses
"""

from genimg.contrib.draw_things_poc.catalog import decode_metadata_override
from genimg.contrib.draw_things_poc.client import DrawThingsClient
from genimg.contrib.draw_things_poc.provider import DrawThingsPoCProvider
from genimg.contrib.draw_things_poc.types import (
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
    "DrawThingsPoCProvider",
    "LoraInfo",
    "ModelInfo",
    "TextualInversionInfo",
    "UpscalerInfo",
    "ZooCatalog",
    "decode_metadata_override",
]
