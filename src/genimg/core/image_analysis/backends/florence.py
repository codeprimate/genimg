"""
Florence-2 backend for image captioning (prose description).

Uses the official API: florence-community/Florence-2-base with
AutoProcessor + Florence2ForConditionalGeneration (no custom tokenizer).
Supports <CAPTION>, <DETAILED_CAPTION>, <MORE_DETAILED_CAPTION> task prompts.
"""

from __future__ import annotations

from typing import Any

from PIL import Image

from genimg.core.image_analysis.backends.base import DescribeBackend

# Task prompts for caption verbosity (single source of truth; used by api and CLI/Gradio)
CAPTION_TASK_PROMPTS = {
    "brief": "<CAPTION>",
    "detailed": "<DETAILED_CAPTION>",
    "more_detailed": "<MORE_DETAILED_CAPTION>",
}

# Official Hugging Face model: use florence-community (not microsoft/) so the
# built-in processor and tokenizer work without trust_remote_code / image_token hacks.
MODEL_ID = "florence-community/Florence-2-base"


def _get_device_and_dtype() -> tuple[Any, Any]:
    import torch

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float16 if device.type == "cuda" else torch.float32
    return device, dtype


class FlorenceBackend(DescribeBackend):
    """
    Florence-2 captioning backend. Lazy-loads on first caption(); unload() frees memory.
    """

    def __init__(self) -> None:
        self._processor: Any = None
        self._model: Any = None
        self._device: Any = None
        self._dtype: Any = None

    def is_loaded(self) -> bool:
        return self._model is not None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from transformers import AutoProcessor, Florence2ForConditionalGeneration

        device, dtype = _get_device_and_dtype()
        self._device = device
        self._dtype = dtype

        # Official 2025/2026 pattern: AutoProcessor + Florence2ForConditionalGeneration
        # only. Do not pass tokenizer/image_processor or trust_remote_code.
        self._processor = AutoProcessor.from_pretrained(MODEL_ID)
        self._model = Florence2ForConditionalGeneration.from_pretrained(
            MODEL_ID,
            torch_dtype=dtype,
        )
        self._model.to(device)
        self._model.eval()

    def caption(self, image: Image.Image, task_prompt: str) -> str:
        """
        Generate caption for a single RGB PIL image.

        task_prompt: one of "<CAPTION>", "<DETAILED_CAPTION>", "<MORE_DETAILED_CAPTION>".
        Returns the caption string.
        """
        self._ensure_loaded()
        import torch

        if image.mode != "RGB":
            image = image.convert("RGB")

        inputs = self._processor(
            text=task_prompt,
            images=image,
            return_tensors="pt",
        )

        # Move to device; cast float tensors (e.g. pixel_values) to model dtype
        def to_device(v: Any) -> Any:
            if hasattr(v, "to"):
                if v.dtype in (torch.float16, torch.float32):
                    return v.to(self._device, dtype=self._dtype)
                return v.to(self._device)
            return v

        inputs = {k: to_device(v) for k, v in inputs.items()}

        with torch.no_grad():
            generated_ids = self._model.generate(
                **inputs,
                max_new_tokens=1024,
                num_beams=3,
            )

        generated_text = self._processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        image_size = image.size  # (width, height)
        parsed = self._processor.post_process_generation(
            generated_text, task=task_prompt, image_size=image_size
        )

        if isinstance(parsed, dict) and task_prompt in parsed:
            return str(parsed[task_prompt]).strip()
        if isinstance(parsed, str):
            return parsed.strip()
        return str(generated_text).strip()

    def unload(self) -> None:
        import torch

        self._processor = None
        self._model = None
        self._device = None
        self._dtype = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
