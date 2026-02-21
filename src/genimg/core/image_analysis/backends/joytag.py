"""
JoyTag backend for image tag prediction.

Lazy-loads fancyfeast/joytag on first predict_tags(); uses SigLIP-style
preprocessing (448x448, pad to square, specific mean/std). Returns list of
(tag, score) above threshold.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import torch
import torchvision.transforms.functional as TVF
from PIL import Image

from genimg.core.image_analysis.backends.base import DescribeBackend

MODEL_REPO = "fancyfeast/joytag"

# SigLIP-style normalization (not ImageNet); per Space app
_MEAN = [0.48145466, 0.4578275, 0.40821073]
_STD = [0.26862954, 0.26130258, 0.27577711]


def _prepare_image(image: Image.Image, target_size: int) -> torch.Tensor:
    """Pad to square, resize to target_size, normalize. Returns tensor (C, H, W)."""
    w, h = image.size
    max_dim = max(w, h)
    pad_left = (max_dim - w) // 2
    pad_top = (max_dim - h) // 2
    padded = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
    padded.paste(image, (pad_left, pad_top))
    if max_dim != target_size:
        padded = padded.resize((target_size, target_size), Image.BICUBIC)
    tensor = TVF.pil_to_tensor(padded) / 255.0
    tensor = TVF.normalize(tensor, mean=_MEAN, std=_STD)
    return cast(torch.Tensor, tensor)


class JoyTagBackend(DescribeBackend):
    """
    JoyTag tag-prediction backend. Lazy-loads on first predict_tags(); unload() frees memory.
    """

    def __init__(self) -> None:
        self._model: Any = None
        self._top_tags: list[str] = []
        self._model_path: Path | None = None

    def is_loaded(self) -> bool:
        return self._model is not None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from huggingface_hub import snapshot_download

        from genimg.core.image_analysis.backends._joytag_models import VisionModel

        path = Path(snapshot_download(MODEL_REPO))
        self._model_path = path
        self._model = VisionModel.load_model(path, device=None)
        self._model.eval()
        with (path / "top_tags.txt").open() as f:
            self._top_tags = [line.strip() for line in f if line.strip()]

    def predict_tags(self, image: Image.Image, threshold: float = 0.4) -> list[tuple[str, float]]:
        """
        Predict tags for a single RGB PIL image. Returns list of (tag, score) above threshold.
        """
        self._ensure_loaded()
        if image.mode != "RGB":
            image = image.convert("RGB")
        image_tensor = _prepare_image(image, self._model.image_size)
        batch = {"image": image_tensor.unsqueeze(0)}
        with torch.no_grad():
            preds = self._model(batch)
            tag_preds = preds["tags"].sigmoid().cpu()[0]
        result: list[tuple[str, float]] = []
        for i, tag in enumerate(self._top_tags):
            score = float(tag_preds[i])
            if score >= threshold:
                result.append((tag, score))
        result.sort(key=lambda x: -x[1])
        return result

    def unload(self) -> None:
        import torch

        self._model = None
        self._top_tags = []
        self._model_path = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
