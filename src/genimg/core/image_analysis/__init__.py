"""
Image analysis (reference image description) for genimg.

Public API: describe_image, unload_describe_models, get_description.
"""

from genimg.core.image_analysis.api import (
    describe_image,
    get_description,
    unload_describe_models,
)

__all__ = ["describe_image", "get_description", "unload_describe_models"]
