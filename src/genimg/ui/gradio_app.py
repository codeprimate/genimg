"""
Gradio web UI for genimg.

Single-page UI: prompt, optional optimization, optional reference image,
generate with progress and cancellation, view/download result (JPG 90, timestamp filename).
Uses only the public API: from genimg import ...
"""

import argparse
import atexit
import base64
import contextlib
import importlib.resources
import json
import os
import tempfile
import threading
import time
from collections.abc import Generator, Sequence
from pathlib import Path
from typing import Any, cast

import gradio as gr

from genimg import (
    APIError,
    CancellationError,
    Config,
    ConfigurationError,
    GenimgError,
    ImageProcessingError,
    NetworkError,
    RequestTimeoutError,
    ValidationError,
    __version__,
    generate_image,
    list_ollama_image_models,
    list_ollama_models,
    optimize_prompt,
    process_reference_image,
    validate_prompt,
)
from genimg.core.image_analysis import (
    describe_image,
    get_description,
    unload_describe_models,
)
from genimg.core.image_gen import resolve_default_image_model
from genimg.core.models import (
    image_models as yaml_image_models,
    merge_optimization_model_choices,
)
from genimg.core.provider_ids import (
    PROVIDER_DRAW_THINGS,
    PROVIDER_OLLAMA,
    PROVIDER_OPENROUTER,
)
from genimg.core.providers import get_registry
from genimg.core.providers.draw_things.lora_choices import (
    DEFAULT_LORA_WEIGHT,
    LoraCatalogResult,
    fetch_draw_things_catalog,
    lora_catalog_hint,
    lora_dropdown_choices,
    model_catalog_hint,
    model_dropdown_choices,
)
from genimg.logging_config import get_logger, log_prompts

logger = get_logger(__name__)

# Max prompt length for logging (large so prompts are effectively never truncated)
_UI_PROMPT_LOG_MAX = 50_000

# Default server port; overridable via GENIMG_UI_PORT
DEFAULT_UI_PORT = 7860
DEFAULT_UI_HOST = "127.0.0.1"

# Base page title (browser tab); status prefixes are prepended during optimize/generate
BASE_PAGE_TITLE = "genimg – AI image generation"

# Image-provider dropdown: include all built-in image providers.
_GRADIO_IMAGE_PROVIDER_CHOICES: tuple[str, ...] = (
    PROVIDER_OPENROUTER,
    PROVIDER_OLLAMA,
    PROVIDER_DRAW_THINGS,
)


def _page_title_with_status(status_tag: str) -> str:
    """Return full page title with optional status prefix for tab."""
    if not status_tag:
        return BASE_PAGE_TITLE
    return f"{status_tag} {BASE_PAGE_TITLE}"


# Shared cancellation event: Generate clears at start, Stop sets it
_cancel_event = threading.Event()

# State key for "which (prompt, ref_hash) the optimized box content was produced for"
OPTIMIZED_FOR_PROMPT = "prompt"
OPTIMIZED_FOR_REF_HASH = "ref_hash"

# Temp paths we create (favicon, reference images, output JPGs); cleaned on process exit
_temp_paths: set[str] = set()
# Temp image paths (reference + output JPGs); cleaned each time Generate is clicked
_temp_image_paths: set[str] = set()


def _register_temp_path(path: str) -> None:
    _temp_paths.add(path)


def _register_temp_image_path(path: str) -> None:
    """Register a temp path that is an image (ref or output); cleaned on each Generate click."""
    _temp_paths.add(path)
    _temp_image_paths.add(path)


def _cleanup_temp_images() -> None:
    """Delete all temp images (reference and output JPGs). Called when Generate is clicked."""
    for path in _temp_image_paths:
        with contextlib.suppress(OSError):
            Path(path).unlink(missing_ok=True)
        _temp_paths.discard(path)
    _temp_image_paths.clear()


def _cleanup_temp_paths() -> None:
    for path in _temp_paths:
        with contextlib.suppress(OSError):
            Path(path).unlink(missing_ok=True)


atexit.register(_cleanup_temp_paths)


def _initial_optimized_for_state() -> dict[str, Any]:
    """Initial value for optimized_for_state (JSON-serializable for Gradio)."""
    return {OPTIMIZED_FOR_PROMPT: "", OPTIMIZED_FOR_REF_HASH: None}


def _coerce_optimized_for_state(value: Any) -> dict[str, Any]:
    """Normalize Gradio State to a dict (handles None, JSON string, or legacy shapes)."""
    if isinstance(value, dict):
        return {
            OPTIMIZED_FOR_PROMPT: _normalize_prompt(value.get(OPTIMIZED_FOR_PROMPT)),
            OPTIMIZED_FOR_REF_HASH: value.get(OPTIMIZED_FOR_REF_HASH),
        }
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return _initial_optimized_for_state()
        if isinstance(parsed, dict):
            return _coerce_optimized_for_state(parsed)
    return _initial_optimized_for_state()


def _normalize_prompt(s: str | None) -> str:
    """Normalize prompt for state store/compare so whitespace differences don't trigger re-optimize."""
    return (s or "").strip()


# Logo assets (package data); populated on first use
_logo_favicon_path: str | None = None


def _get_favicon_path() -> str | None:
    """Return a path to the package favicon for Gradio. Uses a temp copy so it works from zip installs."""
    global _logo_favicon_path
    if _logo_favicon_path is not None:
        return _logo_favicon_path
    try:
        ref = (
            importlib.resources.files("genimg")
            .joinpath("assets")
            .joinpath("logo")
            .joinpath("favicon.ico")
        )
        data = ref.read_bytes()
    except FileNotFoundError:
        return None
    fd, path = tempfile.mkstemp(suffix=".ico", prefix="genimg_favicon_")
    os.close(fd)
    Path(path).write_bytes(data)
    _logo_favicon_path = path
    _register_temp_path(path)
    return path


def get_logo_path(size: int = 128) -> str | None:
    """Return a path to the logo PNG of the given size (16, 32, 48, 64, 128, 256, 512). None if missing."""
    try:
        ref = (
            importlib.resources.files("genimg")
            .joinpath("assets")
            .joinpath("logo")
            .joinpath(f"logo_{size}.png")
        )
        with importlib.resources.as_file(ref) as f:
            return str(f) if f.is_file() else None
    except (FileNotFoundError, OSError):
        return None


def _logo_data_url(size: int = 64) -> str | None:
    """Return a data URL for the logo PNG (for embedding in HTML), or None if missing."""
    try:
        ref = (
            importlib.resources.files("genimg")
            .joinpath("assets")
            .joinpath("logo")
            .joinpath(f"logo_{size}.png")
        )
        data = ref.read_bytes()
    except FileNotFoundError:
        return None
    b64 = base64.standard_b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _provider_supports_reference(provider_id: str | None) -> bool:
    """Return whether provider supports reference images (unknown -> False)."""
    if provider_id is None or not isinstance(provider_id, str):
        return False
    impl = get_registry().get(provider_id)
    if impl is None:
        return False
    return bool(getattr(impl, "supports_reference_image", True))


def _reference_b64_for_generate(provider_id: str | None, ref_b64: str | None) -> str | None:
    """Return reference payload only when provider supports reference images."""
    if not ref_b64:
        return None
    if not _provider_supports_reference(provider_id):
        return None
    return ref_b64


def _effective_provider_for_ui(provider: str | None, config: Config) -> str:
    """Resolve provider for UI side decisions (ref gating, unload behavior)."""
    if provider is not None and isinstance(provider, str) and provider.strip():
        return provider
    default_provider = getattr(config, "default_image_provider", PROVIDER_OPENROUTER)
    if not isinstance(default_provider, str) or not default_provider.strip():
        return PROVIDER_OPENROUTER
    return default_provider


def _draw_things_checkpoint_for_generate(
    *,
    provider_eff: str,
    model: str | None,
    config: Config,
) -> str | None:
    """Return the Draw Things checkpoint filename chosen in the UI."""
    if provider_eff != PROVIDER_DRAW_THINGS:
        return model
    selected = (model or "").strip()
    if not selected or selected == _CHECKPOINT_NONE:
        return None
    return selected


def _checkpoint_ui_choices(
    filenames: list[str],
    catalog_pairs: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Gradio dropdown choices as ``(display_label, checkpoint_filename)``."""
    label_by_file = {file_name: label for file_name, label in catalog_pairs}
    choices: list[tuple[str, str]] = [("— select checkpoint —", _CHECKPOINT_NONE)]
    for file_name in filenames:
        label = label_by_file.get(file_name, file_name)
        choices.append((label, file_name))
    return choices


_CHECKPOINT_NONE = ""
_LORA_NONE = ""
DRAW_THINGS_LORA_SLOT_COUNT = 3


def _lora_ui_dropdown_choices(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Gradio dropdown choices as ``(label, value)`` with a leading none option."""
    return [("— none —", _LORA_NONE)] + [(label, file_name) for file_name, label in pairs]


def _fetch_draw_things_ui_catalog() -> tuple[
    list[str], list[tuple[str, str]], list[tuple[str, str]], str
]:
    """Fetch Draw Things checkpoints + LoRAs from the live app catalog."""
    config = Config.from_env()
    result = fetch_draw_things_catalog(config)
    catalog_model_pairs = model_dropdown_choices(result.models)
    catalog_files = [file_name for file_name, _ in catalog_model_pairs]
    lora_pairs = lora_dropdown_choices(result.loras)
    model_hint = model_catalog_hint(
        result,
        host=config.draw_things_host,
        port=config.draw_things_port,
    )
    lora_hint = lora_catalog_hint(
        LoraCatalogResult(
            loras=result.loras,
            reachable=result.reachable,
            catalog_published=result.catalog_published,
        ),
        host=config.draw_things_host,
        port=config.draw_things_port,
    )
    combined_hint = "\n\n".join(h for h in (model_hint, lora_hint) if h)
    return catalog_files, catalog_model_pairs, lora_pairs, combined_hint


def _parse_lora_slots(
    files: Sequence[str | None],
    weights: Sequence[float],
) -> tuple[tuple[str, float], ...] | None:
    """Return explicit LoRA stack, or ``None`` when all slots are empty (use preset defaults)."""
    out: list[tuple[str, float]] = []
    seen: set[str] = set()
    for file_name, weight in zip(files, weights, strict=True):
        f = (file_name or "").strip()
        if not f or f == _LORA_NONE:
            continue
        if f in seen:
            continue
        seen.add(f)
        out.append((f, float(weight)))
    return tuple(out) if out else None


def _apply_draw_things_loras(
    config: Config,
    provider: str | None,
    files: Sequence[str | None],
    weights: Sequence[float],
) -> None:
    """Set ``config.draw_things_loras`` from UI slot values when provider is Draw Things."""
    config.draw_things_loras = None
    provider_eff = _effective_provider_for_ui(provider, config)
    if provider_eff != PROVIDER_DRAW_THINGS:
        return
    parsed = _parse_lora_slots(files, weights)
    if parsed is not None:
        config.draw_things_loras = parsed


def _empty_lora_slots() -> tuple[list[str], list[float]]:
    """Return cleared LoRA slot values (empty selection, default weight)."""
    return (
        [_LORA_NONE] * DRAW_THINGS_LORA_SLOT_COUNT,
        [DEFAULT_LORA_WEIGHT] * DRAW_THINGS_LORA_SLOT_COUNT,
    )


def _load_model_choices() -> tuple[
    list[str],
    list[str],
    str,
    str,
    str,
    list[str],
    str,
]:
    """
    Load model dropdown choices from models.yaml and config.
    Returns (image_models, ollama_image_models, default_image_provider,
             default_image_model, default_ollama_model, optimization_model_choices,
             default_optimization_model).
    """
    image_models: list[str] = list(yaml_image_models())
    config = Config.from_env()
    default_image_yaml = config.default_image_model
    if default_image_yaml and default_image_yaml not in image_models:
        image_models = [default_image_yaml] + [m for m in image_models if m != default_image_yaml]

    ollama_image_models: list[str] = list_ollama_image_models()
    default_ollama = config.default_ollama_image_model
    if default_ollama and default_ollama not in ollama_image_models:
        ollama_image_models = [default_ollama] + ollama_image_models
    elif default_ollama and ollama_image_models:
        ollama_image_models = [default_ollama] + [
            m for m in ollama_image_models if m != default_ollama
        ]

    default_image_provider: str = config.default_image_provider

    if default_image_provider == PROVIDER_OPENROUTER:
        default_image_model: str = config.default_image_model
    elif default_image_provider == PROVIDER_DRAW_THINGS:
        default_image_model = _CHECKPOINT_NONE
    else:
        default_image_model = default_ollama

    default_opt: str = config.default_optimization_model
    opt_models = merge_optimization_model_choices(
        default=default_opt,
        installed=list_ollama_models(config),
    )

    return (
        image_models,
        ollama_image_models,
        default_image_provider,
        default_image_model,
        default_ollama,
        opt_models,
        default_opt,
    )


# Max length for browser notification body (truncate long error messages)
_NOTIFY_BODY_MAX_LEN = 80


def _notification_body(prefix: str, message: str) -> str:
    """Build a short notification body; truncate to _NOTIFY_BODY_MAX_LEN."""
    s = f"{prefix}{message}"
    if len(s) > _NOTIFY_BODY_MAX_LEN:
        return s[: _NOTIFY_BODY_MAX_LEN - 1] + "…"
    return s


def _generate_notify_msg_on_error(exc: BaseException) -> str:
    """Notification message for generate flow on error; empty for user cancellation."""
    if isinstance(exc, CancellationError):
        return ""
    return _notification_body("Generation failed: ", _exception_to_message(exc))


def _optimize_notify_msg_on_error(exc: BaseException) -> str:
    """Notification message for optimize flow on error; empty for user cancellation."""
    if isinstance(exc, CancellationError):
        return ""
    return _notification_body("Optimization failed: ", _exception_to_message(exc))


def _exception_to_message(exc: BaseException) -> str:
    """Map library and known exceptions to a short user-facing message (same as CLI)."""
    if isinstance(exc, ValidationError):
        msg = exc.args[0] if exc.args else "Validation failed."
        if getattr(exc, "field", None):
            msg = f"{msg} (field: {exc.field})"
        return msg
    if isinstance(exc, ConfigurationError):
        return exc.args[0] if exc.args else "Invalid configuration."
    if isinstance(exc, ImageProcessingError):
        return exc.args[0] if exc.args else "Image processing failed."
    if isinstance(exc, CancellationError):
        return "Cancelled."
    if isinstance(exc, (APIError, NetworkError, RequestTimeoutError)):
        return exc.args[0] if exc.args else "API or network error."
    if isinstance(exc, GenimgError):
        return exc.args[0] if exc.args else "An error occurred."
    return str(exc) if exc.args else "An unexpected error occurred."


def _format_status(message: str, status_type: str = "info") -> str:
    """
    Format a status message with color and icon for better UX.

    Args:
        message: The status message text.
        status_type: One of "info", "success", "error", "warning", "idle".

    Returns:
        HTML-formatted status string.
    """
    if status_type == "success":
        icon = "✅"
        color = "#10b981"  # green-500
        bg_color = "#d1fae5"  # green-100
    elif status_type == "error":
        icon = "❌"
        color = "#ef4444"  # red-500
        bg_color = "#fee2e2"  # red-100
    elif status_type == "warning":
        icon = "⚠️"
        color = "#f59e0b"  # amber-500
        bg_color = "#fef3c7"  # amber-100
    elif status_type == "info":
        icon = "ℹ️"
        color = "#3b82f6"  # blue-500
        bg_color = "#dbeafe"  # blue-100
    else:  # idle
        return ""

    # Use inline styles for reliability across themes
    return f"""<div style="padding: 12px 16px; border-radius: 8px; background-color: {bg_color}; border-left: 4px solid {color}; margin: 8px 0;">
    <span style="font-size: 16px; margin-right: 8px;">{icon}</span>
    <span style="color: {color}; font-weight: 500;">{message}</span>
</div>"""


def _reference_source_for_process(value: Any) -> str | None:
    """
    Get a source suitable for process_reference_image from Gradio Image value.

    Gradio can return: path str, dict with 'path' or 'url' (data URL), or PIL Image.
    We normalize to a path (str), data URL (str), or PIL for temp-file save.
    """
    if value is None:
        return None
    # PIL Image (e.g. Gradio type="pil" or some versions): save to temp file and return path
    if hasattr(value, "size") and hasattr(value, "save"):
        try:
            fd, path = tempfile.mkstemp(suffix=".png", prefix="genimg_ref_")
            os.close(fd)
            value.save(path, "PNG")
            _register_temp_image_path(path)
            return path
        except Exception:
            return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, dict):
        path_val = value.get("path")
        url_val = value.get("url")
        if path_val and isinstance(path_val, str) and path_val.strip():
            return cast(str, path_val)
        if url_val and isinstance(url_val, str) and url_val.strip():
            return cast(str, url_val)  # data URL or blob; reference module handles data URL
        return None
    # str path or Path
    return str(value)


def _run_generate(
    prompt: str,
    optimize: bool,
    reference_value: Any,
    provider: str | None,
    model: str | None,
    optimization_model: str | None = None,
    cancel_check: Any | None = None,
    lora_files: Sequence[str | None] | None = None,
    lora_weights: Sequence[float] | None = None,
) -> tuple[str | None, Any | None, str]:
    """
    Run the generate flow: validate, optional optimize, generate, return (status, image, status_msg).

    Returns:
        (status_text, image_for_display, status_message)
        On success: status_message like "Done in X.Xs", image = path to JPG for display.
        On error/cancel: status_message = error text, image = None.
    """
    if not prompt or not prompt.strip():
        return None, None, "Enter a prompt to generate."

    config = Config.from_env()
    provider_eff = _effective_provider_for_ui(provider, config)
    try:
        config.validate()
    except ConfigurationError as e:
        return None, None, _exception_to_message(e)

    try:
        validate_prompt(prompt)
    except ValidationError as e:
        return None, None, _exception_to_message(e)

    ref_b64: str | None = None
    ref_hash: str | None = None
    ref_source = _reference_source_for_process(reference_value)
    if ref_source is not None:
        try:
            ref_b64, ref_hash = process_reference_image(ref_source, config=config)
        except (ValidationError, ImageProcessingError, FileNotFoundError) as e:
            return None, None, _exception_to_message(e)

    effective_prompt = prompt
    if optimize:
        config.optimization_enabled = True
        try:
            effective_prompt = optimize_prompt(
                prompt,
                model=optimization_model,
                reference_hash=ref_hash,
                config=config,
                cancel_check=cancel_check,
            )
        except (ValidationError, APIError, RequestTimeoutError, CancellationError) as e:
            return None, None, _exception_to_message(e)

    try:
        ref_b64_to_send = _reference_b64_for_generate(provider_eff, ref_b64)
        resolved_model = _draw_things_checkpoint_for_generate(
            provider_eff=provider_eff,
            model=model,
            config=config,
        )
        _apply_draw_things_loras(
            config,
            provider,
            lora_files or (),
            lora_weights or (),
        )
        result = generate_image(
            effective_prompt,
            model=resolved_model or None,
            reference_images_b64=[ref_b64_to_send] if ref_b64_to_send else None,
            provider=provider,
            config=config,
            cancel_check=cancel_check,
        )
    except (
        ValidationError,
        APIError,
        NetworkError,
        RequestTimeoutError,
        CancellationError,
    ) as e:
        return None, None, _exception_to_message(e)

    # Output: JPG quality 90, timestamp filename (per plan)
    elapsed = result.generation_time
    ts = int(time.time())
    out_path = Path(tempfile.gettempdir()) / f"{ts}.jpg"
    result.image.save(str(out_path), "JPEG", quality=90)
    _register_temp_image_path(str(out_path))
    return f"Done in {elapsed:.1f}s", str(out_path), f"Done in {elapsed:.1f}s"


def _run_generate_stream(
    prompt: str,
    optimize: bool,
    optimized_prompt_value: str | None,
    reference_value: Any,
    provider: str | None,
    model: str | None,
    optimization_model: str | None = None,
    cancel_check: Any | None = None,
    optimized_for_state: dict[str, Any] | None = None,
    use_description: bool = False,
    description_method: str = "prose",
    description_verbosity: str = "detailed",
    optimize_thinking: bool = False,
    optimize_format: str = "prose",
    lora_files: Sequence[str | None] | None = None,
    lora_weights: Sequence[float] | None = None,
) -> Generator[tuple[str, str | None, bool, bool, str, dict[str, Any], str, str], None, None]:
    """
    Generate flow: use Optimized prompt box only when it was produced for the current
    (prompt, ref_hash); otherwise run optimize when checkbox on, else use Prompt.
    Yields (status, img_path, gen_on, stop_on, optimized_box_value, optimized_for_state, page_title, notify_msg).
    """
    state = _coerce_optimized_for_state(optimized_for_state)
    # Preserve exact box content (user may have edited); only overwrite when we run optimize
    box_value = optimized_prompt_value if optimized_prompt_value is not None else ""
    has_box_content = bool((box_value or "").strip())

    if not prompt or not prompt.strip():
        yield (
            _format_status("Enter a prompt to generate.", "warning"),
            None,
            True,
            False,
            box_value,
            state,
            BASE_PAGE_TITLE,
            "",
        )
        return
    logger.info("Generate requested")
    if log_prompts():
        truncated = (
            prompt if len(prompt) <= _UI_PROMPT_LOG_MAX else prompt[:_UI_PROMPT_LOG_MAX] + "..."
        )
        logger.info("Prompt: %s", truncated)
    config = Config.from_env()
    provider_eff = _effective_provider_for_ui(provider, config)
    config.optimize_thinking = optimize_thinking
    config.optimize_format = optimize_format
    try:
        config.validate()
    except ConfigurationError as e:
        yield (
            _format_status(_exception_to_message(e), "error"),
            None,
            True,
            False,
            box_value,
            state,
            BASE_PAGE_TITLE,
            _notification_body("Generation failed: ", _exception_to_message(e)),
        )
        return
    try:
        validate_prompt(prompt)
    except ValidationError as e:
        yield (
            _format_status(_exception_to_message(e), "error"),
            None,
            True,
            False,
            box_value,
            state,
            BASE_PAGE_TITLE,
            _notification_body("Generation failed: ", _exception_to_message(e)),
        )
        return
    ref_b64: str | None = None
    ref_hash: str | None = None
    ref_source = _reference_source_for_process(reference_value)
    if ref_source is not None:
        try:
            ref_b64, ref_hash = process_reference_image(ref_source, config=config)
        except (ValidationError, ImageProcessingError, FileNotFoundError) as e:
            yield (
                _format_status(_exception_to_message(e), "error"),
                None,
                True,
                False,
                box_value,
                state,
                BASE_PAGE_TITLE,
                _notification_body("Generation failed: ", _exception_to_message(e)),
            )
            return
    description: str | None = None
    if use_description and ref_source is not None:
        try:
            description = get_description(
                ref_source,
                ref_hash,
                method=description_method,
                verbosity=description_verbosity or "detailed",
            )
            if provider_eff == PROVIDER_OLLAMA:
                unload_describe_models()
        except Exception as e:
            yield (
                _format_status(_exception_to_message(e), "error"),
                None,
                True,
                False,
                box_value,
                state,
                BASE_PAGE_TITLE,
                _notification_body("Generation failed: ", _exception_to_message(e)),
            )
            return
    ref_b64_to_send = _reference_b64_for_generate(provider_eff, ref_b64)
    # Use optimized box only if it was produced for this exact (prompt, ref_hash).
    # Normalize prompt so whitespace differences don't trigger re-optimize and overwrite user edits.
    state_matches = (
        _normalize_prompt(state.get(OPTIMIZED_FOR_PROMPT)) == _normalize_prompt(prompt)
        and state.get(OPTIMIZED_FOR_REF_HASH) == ref_hash
    )
    if has_box_content and state_matches and optimize:
        # Use current box content (may be user-edited); do not run optimize or overwrite box
        effective_prompt = box_value
    elif has_box_content and not state_matches and optimize:
        # Prompt or ref changed; re-optimize for current prompt
        config.optimization_enabled = True
        yield (
            _format_status("Optimizing…", "info"),
            None,
            False,
            True,
            box_value,
            state,
            _page_title_with_status("[Optimizing]"),
            "",
        )
        try:
            effective_prompt = optimize_prompt(
                prompt,
                model=optimization_model,
                reference_hash=ref_hash,
                reference_description=description if (use_description and description) else None,
                config=config,
                cancel_check=cancel_check,
            )
            box_value = effective_prompt
            state = {
                OPTIMIZED_FOR_PROMPT: _normalize_prompt(prompt),
                OPTIMIZED_FOR_REF_HASH: ref_hash,
            }
        except (ValidationError, APIError, RequestTimeoutError, CancellationError) as e:
            yield (
                _format_status(_exception_to_message(e), "error"),
                None,
                True,
                False,
                box_value,
                state,
                BASE_PAGE_TITLE,
                _generate_notify_msg_on_error(e),
            )
            return
    elif has_box_content and not state_matches and not optimize:
        # Stale box from different prompt/ref; user has optimization off so use raw prompt
        effective_prompt = prompt
    elif optimize:
        config.optimization_enabled = True
        yield (
            _format_status("Optimizing…", "info"),
            None,
            False,
            True,
            box_value,
            state,
            _page_title_with_status("[Optimizing]"),
            "",
        )
        try:
            effective_prompt = optimize_prompt(
                prompt,
                model=optimization_model,
                reference_hash=ref_hash,
                reference_description=description if (use_description and description) else None,
                config=config,
                cancel_check=cancel_check,
            )
            box_value = effective_prompt
            state = {
                OPTIMIZED_FOR_PROMPT: _normalize_prompt(prompt),
                OPTIMIZED_FOR_REF_HASH: ref_hash,
            }
        except (ValidationError, APIError, RequestTimeoutError, CancellationError) as e:
            yield (
                _format_status(_exception_to_message(e), "error"),
                None,
                True,
                False,
                box_value,
                state,
                BASE_PAGE_TITLE,
                _generate_notify_msg_on_error(e),
            )
            return
    else:
        effective_prompt = prompt
    yield (
        _format_status("Generating…", "info"),
        None,
        False,
        True,
        box_value,
        state,
        _page_title_with_status("[Generating]"),
        "",
    )
    try:
        resolved_model = _draw_things_checkpoint_for_generate(
            provider_eff=provider_eff,
            model=model,
            config=config,
        )
        _apply_draw_things_loras(
            config,
            provider,
            lora_files or (),
            lora_weights or (),
        )
        result = generate_image(
            effective_prompt,
            model=resolved_model or None,
            reference_images_b64=[ref_b64_to_send] if ref_b64_to_send else None,
            provider=provider,
            config=config,
            cancel_check=cancel_check,
        )
    except (
        ValidationError,
        APIError,
        NetworkError,
        RequestTimeoutError,
        CancellationError,
    ) as e:
        yield (
            _format_status(_exception_to_message(e), "error"),
            None,
            True,
            False,
            gr.skip(),  # preserve user edits made during generation
            state,
            BASE_PAGE_TITLE,
            _generate_notify_msg_on_error(e),
        )
        return
    elapsed = result.generation_time
    ts = int(time.time())
    out_path = Path(tempfile.gettempdir()) / f"{ts}.jpg"
    result.image.save(str(out_path), "JPEG", quality=90)
    _register_temp_image_path(str(out_path))
    yield (
        _format_status(f"Done in {elapsed:.1f}s", "success"),
        str(out_path),
        True,
        False,
        gr.skip(),  # preserve user edits made during generation
        state,
        _page_title_with_status("[DONE]"),
        f"Done in {elapsed:.1f}s",
    )


def _generate_click_handler(
    p: str,
    opt: bool,
    opt_text: str,
    ref: Any,
    provider: str | None,
    mod: str | None,
    opt_mod: str | None,
    optimized_for_state: dict[str, Any] | None = None,
    use_description: bool = False,
    desc_method_ui: str = "Prose (Florence)",
    desc_verbosity: str = "detailed",
    optimize_thinking: bool = False,
    optimize_format_ui: str = "Prose",
    lora_file_0: str | None = None,
    lora_file_1: str | None = None,
    lora_file_2: str | None = None,
    lora_weight_0: float = DEFAULT_LORA_WEIGHT,
    lora_weight_1: float = DEFAULT_LORA_WEIGHT,
    lora_weight_2: float = DEFAULT_LORA_WEIGHT,
) -> Generator[tuple[Any, ...], None, None]:
    """Generate button logic: clear cancel, run stream, yield updates. Used by UI and tests."""
    logger.debug("Generate clicked")
    _cleanup_temp_images()
    _cancel_event.clear()
    state = _coerce_optimized_for_state(optimized_for_state)
    ui_to_method = {"Prose (Florence)": "prose", "Tags (JoyTag)": "tags"}
    description_method = ui_to_method.get(desc_method_ui, "prose")
    optimize_format = "json" if optimize_format_ui == "JSON" else "prose"
    try:
        for (
            status_msg,
            img_path,
            gen_on,
            stop_on,
            box_val,
            new_state,
            page_title,
            notify_msg,
        ) in _run_generate_stream(
            p,
            opt,
            opt_text,
            ref,
            provider,
            mod,
            optimization_model=opt_mod,
            cancel_check=lambda: _cancel_event.is_set(),
            optimized_for_state=state,
            use_description=use_description,
            description_method=description_method,
            description_verbosity=desc_verbosity or "detailed",
            optimize_thinking=optimize_thinking,
            optimize_format=optimize_format,
            lora_files=(lora_file_0, lora_file_1, lora_file_2),
            lora_weights=(lora_weight_0, lora_weight_1, lora_weight_2),
        ):
            state = new_state
            yield (
                status_msg,
                img_path,
                gr.update(interactive=gen_on),
                gr.update(interactive=stop_on),
                box_val,
                state,
                page_title,
                notify_msg,
            )
    except GenimgError as e:
        yield (
            _format_status(_exception_to_message(e), "error"),
            None,
            gr.update(interactive=True),
            gr.update(interactive=False),
            opt_text,
            state,
            BASE_PAGE_TITLE,
            _generate_notify_msg_on_error(e),
        )
    except Exception as e:
        yield (
            _format_status(str(e), "error"),
            None,
            gr.update(interactive=True),
            gr.update(interactive=False),
            opt_text,
            state,
            BASE_PAGE_TITLE,
            _notification_body("Generation failed: ", str(e)),
        )


def _optimize_click_handler(
    p: str,
    ref: Any,
    opt_mod: str | None,
    optimized_for_state: dict[str, Any] | None = None,
    use_description: bool = False,
    desc_method_ui: str = "Prose (Florence)",
    desc_verbosity: str = "detailed",
    provider: str | None = None,
    optimize_thinking: bool = False,
    optimize_format_ui: str = "Prose",
) -> Generator[tuple[Any, ...], None, None]:
    """Optimize button logic: clear cancel, run stream, yield updates. Used by UI and tests."""
    logger.debug("Optimize clicked")
    _cancel_event.clear()
    state = _coerce_optimized_for_state(optimized_for_state)
    ui_to_method = {"Prose (Florence)": "prose", "Tags (JoyTag)": "tags"}
    description_method = ui_to_method.get(desc_method_ui, "prose")
    optimize_format = "json" if optimize_format_ui == "JSON" else "prose"
    try:
        for (
            status_msg,
            opt_text,
            opt_on,
            stop_on,
            gen_on,
            state_update,
            page_title,
            notify_msg,
        ) in _run_optimize_only_stream(
            p,
            ref,
            optimization_model=opt_mod,
            cancel_check=lambda: _cancel_event.is_set(),
            use_description=use_description,
            description_method=description_method,
            description_verbosity=desc_verbosity or "detailed",
            provider=provider,
            optimize_thinking=optimize_thinking,
            optimize_format=optimize_format,
        ):
            if state_update is not None:
                state = state_update
            yield (
                status_msg,
                opt_text,
                gr.update(interactive=opt_on),
                gr.update(interactive=stop_on),
                gr.update(interactive=gen_on),
                state,
                page_title,
                notify_msg,
            )
    except GenimgError as e:
        yield (
            _format_status(_exception_to_message(e), "error"),
            "",
            gr.update(interactive=True),
            gr.update(interactive=False),
            gr.update(interactive=True),
            state,
            BASE_PAGE_TITLE,
            _optimize_notify_msg_on_error(e),
        )
    except Exception as e:
        yield (
            _format_status(str(e), "error"),
            "",
            gr.update(interactive=True),
            gr.update(interactive=False),
            gr.update(interactive=True),
            state,
            BASE_PAGE_TITLE,
            _notification_body("Optimization failed: ", str(e)),
        )


def _stop_click_handler() -> tuple[Any, Any, Any, str]:
    """Stop button logic: set cancel event, restore button states, status message, reset page title."""
    _cancel_event.set()
    return (
        _format_status("Stopped.", "info"),
        gr.update(interactive=True),
        gr.update(interactive=False),
        BASE_PAGE_TITLE,
    )


def _prompt_change_handler(text: str) -> tuple[Any, Any]:
    """Prompt change: enable Generate and Optimize when prompt is non-empty."""
    enabled = bool(text and text.strip())
    return gr.update(interactive=enabled), gr.update(interactive=enabled)


def _optimize_checkbox_handler(enabled: bool) -> Any:
    """Update tab label based on optimization checkbox state."""
    label = "Optimized Prompt (enabled)" if enabled else "Optimized Prompt"
    return gr.update(label=label)


def _run_optimize_only_stream(
    prompt: str,
    reference_value: Any,
    optimization_model: str | None = None,
    cancel_check: Any | None = None,
    use_description: bool = False,
    description_method: str = "prose",
    description_verbosity: str = "detailed",
    provider: str | None = None,
    optimize_thinking: bool = False,
    optimize_format: str = "prose",
) -> Generator[tuple[str, str, bool, bool, bool, dict[str, Any] | None, str, str], None, None]:
    """
    Run optimization only; yields (status_msg, optimized_text, optimize_btn_on, stop_btn_on, generate_btn_on, state_update, page_title, notify_msg).
    state_update is None for intermediate yields; on success final yield it is {prompt, ref_hash}.
    """
    prompt_ok = bool(prompt and prompt.strip())
    if not prompt_ok:
        yield (
            _format_status("Enter a prompt to optimize.", "warning"),
            "",
            True,
            False,
            False,
            None,
            BASE_PAGE_TITLE,
            "",
        )
        return
    logger.info("Optimize requested")
    if log_prompts():
        truncated = (
            prompt if len(prompt) <= _UI_PROMPT_LOG_MAX else prompt[:_UI_PROMPT_LOG_MAX] + "..."
        )
        logger.info("Prompt: %s", truncated)
    config = Config.from_env()
    provider_eff = _effective_provider_for_ui(provider, config)
    config.optimize_thinking = optimize_thinking
    config.optimize_format = optimize_format
    try:
        config.validate()
    except ConfigurationError as e:
        yield (
            _format_status(_exception_to_message(e), "error"),
            "",
            True,
            False,
            True,
            None,
            BASE_PAGE_TITLE,
            _notification_body("Optimization failed: ", _exception_to_message(e)),
        )
        return
    try:
        validate_prompt(prompt)
    except ValidationError as e:
        yield (
            _format_status(_exception_to_message(e), "error"),
            "",
            True,
            False,
            True,
            None,
            BASE_PAGE_TITLE,
            _notification_body("Optimization failed: ", _exception_to_message(e)),
        )
        return
    ref_hash: str | None = None
    ref_source = _reference_source_for_process(reference_value)
    if ref_source is not None:
        try:
            _, ref_hash = process_reference_image(ref_source, config=config)
        except (ValidationError, ImageProcessingError, FileNotFoundError) as e:
            yield (
                _format_status(_exception_to_message(e), "error"),
                "",
                True,
                False,
                True,
                None,
                BASE_PAGE_TITLE,
                _notification_body("Optimization failed: ", _exception_to_message(e)),
            )
            return
    description: str | None = None
    if use_description and ref_source is not None:
        try:
            description = get_description(
                ref_source,
                ref_hash,
                method=description_method,
                verbosity=description_verbosity or "detailed",
            )
            if provider_eff == PROVIDER_OLLAMA:
                unload_describe_models()
        except Exception as e:
            yield (
                _format_status(_exception_to_message(e), "error"),
                "",
                True,
                False,
                True,
                None,
                BASE_PAGE_TITLE,
                _notification_body("Optimization failed: ", _exception_to_message(e)),
            )
            return
    config.optimization_enabled = True
    yield (
        _format_status("Optimizing…", "info"),
        "",
        False,
        True,
        False,
        None,
        _page_title_with_status("[Optimizing]"),
        "",
    )
    try:
        optimized = optimize_prompt(
            prompt,
            model=optimization_model,
            reference_hash=ref_hash,
            reference_description=description if (use_description and description) else None,
            enable_cache=False,  # Optimize button always forces a fresh run
            config=config,
            cancel_check=cancel_check,
        )
        state_update = {
            OPTIMIZED_FOR_PROMPT: _normalize_prompt(prompt),
            OPTIMIZED_FOR_REF_HASH: ref_hash,
        }
        yield (
            _format_status("Optimized. Edit above if needed, then Generate.", "success"),
            optimized,
            True,
            False,
            True,
            state_update,
            _page_title_with_status("[DONE]"),
            "Optimization complete",
        )
    except (ValidationError, APIError, RequestTimeoutError, CancellationError) as e:
        yield (
            _format_status(_exception_to_message(e), "error"),
            "",
            True,
            False,
            True,
            None,
            BASE_PAGE_TITLE,
            _optimize_notify_msg_on_error(e),
        )


# Message shown when provider does not support reference images
_REF_NOT_SUPPORTED_MSG = "Reference images are not supported for this provider."


def _build_blocks() -> gr.Blocks:
    """Build the Gradio Blocks UI (layout + generate handler, no cancellation yet)."""
    (
        image_models,
        ollama_image_models,
        default_image_provider,
        default_image_model,
        default_ollama,
        opt_models,
        default_opt,
    ) = _load_model_choices()

    # LoRA catalog is fetched when Draw Things is selected (not at UI build time).
    lora_dd_choices = _lora_ui_dropdown_choices([])
    lora_catalog_info = ""
    initial_lora_files, initial_lora_weights = _empty_lora_slots()
    initial_lora_visible = default_image_provider == PROVIDER_DRAW_THINGS

    logo_img = ""
    logo_url = _logo_data_url(64)
    if logo_url:
        logo_img = f'<img src="{logo_url}" alt="genimg" width="64" height="64" style="display: block; flex-shrink: 0;" />'

    header_html = f"""
<div style="display: flex; align-items: center; gap: 32px; margin: 16px 0 24px 0; flex-wrap: wrap;">
    <div style="flex-shrink: 0; display: flex; align-items: center; gap: 16px;">
        {logo_img}
        <h1 style="
            font-size: 2.5em;
            font-weight: 700;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            letter-spacing: -0.02em;
        ">genimg</h1>
    </div>
    <div style="flex: 1; min-width: 200px;">
        <p style="font-size: 1.1em; color: #6b7280; margin: 0 0 4px 0; font-weight: 400;">AI-powered image generation with intelligent prompt optimization</p>
        <p style="font-size: 0.9em; color: #9ca3af; margin: 0; font-weight: 400;">Ollama prompt enhancement • OpenRouter/Draw Things image models • Reference images for supported providers</p>
    </div>
</div>
"""

    with gr.Blocks(title=BASE_PAGE_TITLE) as app:
        gr.HTML(header_html)
        status_html = gr.HTML(value="", visible=True)
        page_title = gr.Textbox(value=BASE_PAGE_TITLE, visible=False, elem_id="genimg-page-title")
        notify_msg = gr.Textbox(value="", visible=False, elem_id="genimg-notify-msg")

        with gr.Row():
            with gr.Column():
                with gr.Tabs():
                    with gr.Tab("Prompt"):
                        prompt_tb = gr.Textbox(
                            label="Prompt",
                            placeholder="Describe the image you want to generate…",
                            lines=12,
                            max_lines=20,
                        )
                    with gr.Tab("Optimized Prompt (enabled)") as optimized_tab:
                        optimize_cb = gr.Checkbox(
                            label="✨ Enable prompt optimization (Ollama)",
                            value=True,
                        )
                        optimized_tb = gr.Textbox(
                            label="Optimized prompt (editable)",
                            placeholder="Click Optimize or run Generate with optimization enabled to fill. Edit then Generate.",
                            lines=8,
                            max_lines=12,
                        )
                        optimization_dd = gr.Dropdown(
                            label="Optimization model (Ollama)",
                            value=default_opt,
                            choices=opt_models,
                            allow_custom_value=True,
                            visible=True,
                            info="Ollama model for prompt optimization.",
                        )
                        think_cb = gr.Checkbox(
                            label="Think",
                            value=False,
                            info="Enable LLM thinking during optimization (slower).",
                        )
                        optimize_format_dd = gr.Dropdown(
                            label="Output format",
                            choices=["Prose", "JSON"],
                            value="Prose",
                            info="Prose: structured labeled sections. JSON: Ideogram 4 schema, assembled to prose for the image model.",
                        )
                        optimize_btn = gr.Button(
                            "Enhance Prompt", variant="secondary", interactive=False
                        )
            with gr.Column():
                with gr.Tabs():
                    with gr.Tab("Reference image"):
                        ref_image = gr.Image(
                            label="Reference image",
                            type="filepath",
                            sources=["upload", "clipboard"],
                            visible=True,
                        )
                    with gr.Tab("Description"):
                        with gr.Row():
                            desc_method_dd = gr.Dropdown(
                                label="Method",
                                choices=["Prose (Florence)", "Tags (JoyTag)"],
                                value="Prose (Florence)",
                                interactive=False,
                            )
                            desc_verbosity_dd = gr.Dropdown(
                                label="Prose verbosity",
                                choices=["brief", "detailed", "more_detailed"],
                                value="detailed",
                                visible=True,
                                interactive=False,
                            )
                        describe_btn = gr.Button("Describe", interactive=False)
                        describe_output_tb = gr.Textbox(
                            label="Description",
                            lines=6,
                            max_lines=12,
                            interactive=False,
                            placeholder="Upload a reference image and click Describe.",
                        )
                use_description_cb = gr.Checkbox(
                    label="Use image description/tags",
                    value=False,
                    interactive=False,
                    info="Use description in optimization; reference images are sent only when the selected provider supports them.",
                )

        with gr.Row():
            with gr.Column(scale=1):
                provider_dd = gr.Dropdown(
                    label="Image provider",
                    choices=list(_GRADIO_IMAGE_PROVIDER_CHOICES),
                    value=default_image_provider,
                    visible=True,
                )
            with gr.Column(scale=1):
                model_dd = gr.Dropdown(
                    label="Image model",
                    value=default_image_model,
                    choices=(
                        image_models
                        if default_image_provider == PROVIDER_OPENROUTER
                        else (
                            _checkpoint_ui_choices([], [])
                            if default_image_provider == PROVIDER_DRAW_THINGS
                            else ollama_image_models
                        )
                    ),
                    allow_custom_value=True,
                    visible=True,
                    info=(
                        "Draw Things checkpoint (.ckpt). Choices refresh from the app when you "
                        "select this provider; type another filename if needed."
                        if default_image_provider == PROVIDER_DRAW_THINGS
                        else "Model for the selected provider. Type a model ID for another."
                    ),
                )
                ref_message = gr.HTML(
                    value=_format_status(_REF_NOT_SUPPORTED_MSG, "warning"),
                    visible=(not _provider_supports_reference(default_image_provider)),
                )

                with gr.Column(visible=initial_lora_visible) as lora_section:
                    lora_info = gr.Markdown(
                        lora_catalog_info,
                        visible=bool(lora_catalog_info.strip()),
                    )
                    lora_dd_0 = gr.Dropdown(
                        label="LoRA 1",
                        choices=lora_dd_choices,
                        value=initial_lora_files[0],
                        allow_custom_value=True,
                    )
                    lora_sl_0 = gr.Slider(
                        label="Weight 1",
                        minimum=0.0,
                        maximum=1.0,
                        step=0.05,
                        value=initial_lora_weights[0],
                    )
                    lora_dd_1 = gr.Dropdown(
                        label="LoRA 2",
                        choices=lora_dd_choices,
                        value=initial_lora_files[1],
                        allow_custom_value=True,
                    )
                    lora_sl_1 = gr.Slider(
                        label="Weight 2",
                        minimum=0.0,
                        maximum=1.0,
                        step=0.05,
                        value=initial_lora_weights[1],
                    )
                    lora_dd_2 = gr.Dropdown(
                        label="LoRA 3",
                        choices=lora_dd_choices,
                        value=initial_lora_files[2],
                        allow_custom_value=True,
                    )
                    lora_sl_2 = gr.Slider(
                        label="Weight 3",
                        minimum=0.0,
                        maximum=1.0,
                        step=0.05,
                        value=initial_lora_weights[2],
                    )

        lora_slot_components: tuple[Any, ...] = (
            lora_dd_0,
            lora_sl_0,
            lora_dd_1,
            lora_sl_1,
            lora_dd_2,
            lora_sl_2,
        )

        def _lora_slot_updates(
            *,
            visible: bool,
            pairs: list[tuple[str, str]],
            hint: str = "",
        ) -> tuple[Any, ...]:
            choices = _lora_ui_dropdown_choices(pairs)
            files, weights = _empty_lora_slots()
            return (
                gr.update(visible=visible),
                gr.update(
                    visible=visible and bool(hint),
                    value=hint,
                ),
                gr.update(value=files[0], choices=choices),
                gr.update(value=weights[0]),
                gr.update(value=files[1], choices=choices),
                gr.update(value=weights[1]),
                gr.update(value=files[2], choices=choices),
                gr.update(value=weights[2]),
            )

        def _on_provider_change(provider: str) -> tuple[Any, ...]:
            if provider == PROVIDER_OLLAMA:
                config = Config.from_env()
                return (
                    gr.update(
                        choices=ollama_image_models,
                        value=config.default_ollama_image_model,
                    ),
                    gr.update(
                        visible=True,
                        value=_format_status(_REF_NOT_SUPPORTED_MSG, "warning"),
                    ),
                    *_lora_slot_updates(visible=False, pairs=[]),
                )
            if provider == PROVIDER_DRAW_THINGS:
                models, catalog_pairs, lora_pairs, hint = _fetch_draw_things_ui_catalog()
                model_choices = _checkpoint_ui_choices(models, catalog_pairs)
                return (
                    gr.update(choices=model_choices, value=_CHECKPOINT_NONE),
                    gr.update(visible=False),
                    *_lora_slot_updates(visible=True, pairs=lora_pairs, hint=hint),
                )
            config = Config.from_env()
            openrouter_default = resolve_default_image_model(
                provider_id=PROVIDER_OPENROUTER, config=config
            )
            if not openrouter_default and image_models:
                openrouter_default = image_models[0]
            return (
                gr.update(choices=image_models, value=openrouter_default),
                gr.update(visible=False),
                *_lora_slot_updates(visible=False, pairs=[]),
            )

        provider_dd.change(
            fn=_on_provider_change,
            inputs=[provider_dd],
            outputs=[
                model_dd,
                ref_message,
                lora_section,
                lora_info,
                *lora_slot_components,
            ],
        )

        def _load_draw_things_catalog_if_selected(provider: str) -> tuple[Any, ...]:
            """Populate checkpoint + LoRA lists from Draw Things when that provider is active."""
            if provider != PROVIDER_DRAW_THINGS:
                return (gr.update(),) + tuple(gr.update() for _ in range(8))
            models, catalog_pairs, lora_pairs, hint = _fetch_draw_things_ui_catalog()
            return (
                gr.update(
                    choices=_checkpoint_ui_choices(models, catalog_pairs),
                    value=_CHECKPOINT_NONE,
                ),
                *_lora_slot_updates(visible=True, pairs=lora_pairs, hint=hint),
            )

        def _refresh_optimization_models() -> Any:
            """Refresh optimization dropdown from live Ollama."""
            config = Config.from_env()
            default_opt = config.default_optimization_model
            choices = merge_optimization_model_choices(
                default=default_opt,
                installed=list_ollama_models(config),
            )
            value = default_opt if default_opt in choices else (choices[0] if choices else "")
            return gr.update(choices=choices, value=value)

        app.load(
            fn=_refresh_optimization_models,
            inputs=[],
            outputs=[optimization_dd],
        )

        app.load(
            fn=_load_draw_things_catalog_if_selected,
            inputs=[provider_dd],
            outputs=[model_dd, lora_section, lora_info, *lora_slot_components],
        )

        def _on_desc_method_change(method: str) -> Any:
            return gr.update(visible=(method == "Prose (Florence)"))

        desc_method_dd.change(
            fn=_on_desc_method_change,
            inputs=[desc_method_dd],
            outputs=[desc_verbosity_dd],
        )

        def _ref_image_change(ref_value: Any) -> tuple[Any, ...]:
            src = _reference_source_for_process(ref_value)
            enabled = src is not None
            cb_update = (
                gr.update(interactive=False, value=False)
                if not enabled
                else gr.update(interactive=True)
            )
            return (
                gr.update(interactive=enabled),
                cb_update,
                gr.update(interactive=enabled),
                gr.update(interactive=enabled),
            )

        ref_image.change(
            fn=_ref_image_change,
            inputs=[ref_image],
            outputs=[describe_btn, use_description_cb, desc_method_dd, desc_verbosity_dd],
        )

        def _describe_click(ref_value: Any, method: str, verbosity: str) -> tuple[str, str]:
            ref_source = _reference_source_for_process(ref_value)
            if ref_source is None:
                return "", _format_status("No reference image.", "warning")
            ui_to_method = {"Prose (Florence)": "prose", "Tags (JoyTag)": "tags"}
            method_val = ui_to_method.get(method, "prose")
            try:
                desc = describe_image(
                    ref_source, method=method_val, verbosity=verbosity or "detailed"
                )
                return (desc or "").strip(), _format_status("Description ready.", "success")
            except Exception as e:
                return "", _format_status(_exception_to_message(e), "error")

        describe_btn.click(
            fn=_describe_click,
            inputs=[ref_image, desc_method_dd, desc_verbosity_dd],
            outputs=[describe_output_tb, status_html],
            concurrency_id="genimg_ui",
        )
        with gr.Row():
            generate_btn = gr.Button("Generate", variant="primary", interactive=False)
            stop_btn = gr.Button("Stop", interactive=False)
        out_image = gr.Image(
            label="Output",
            type="filepath",
            height="70vh",
            elem_id="genimg-output-image",
        )

        optimized_for_state = gr.State(value=_initial_optimized_for_state())

        # Shared queue so generate/optimize/stop/prompt_tb updates run serially (avoids button re-enable race).
        _UI_CONCURRENCY_ID = "genimg_ui"
        _JS_SET_PAGE_TITLE = "function(...args) { if (args.length) document.title = args[args.length - 1] || ''; return args; }"
        _JS_REQUEST_NOTIFICATION_PERMISSION = "function() { if (typeof Notification !== 'undefined' && Notification.permission === 'default') Notification.requestPermission(); }"
        _JS_NOTIFY_IF_MSG = "function(...args) { var n = args.length; if (n > 0 && args[n-1] && typeof Notification !== 'undefined' && Notification.permission === 'granted') { new Notification('genimg', { body: args[n-1] }); var out = args.slice(); out[n-1] = ''; return out; } return args; }"
        _gen_outputs = [
            status_html,
            out_image,
            generate_btn,
            stop_btn,
            optimized_tb,
            optimized_for_state,
            page_title,
            notify_msg,
        ]
        _opt_outputs = [
            status_html,
            optimized_tb,
            optimize_btn,
            stop_btn,
            generate_btn,
            optimized_for_state,
            page_title,
            notify_msg,
        ]

        gen_ev = generate_btn.click(
            fn=_generate_click_handler,
            inputs=[
                prompt_tb,
                optimize_cb,
                optimized_tb,
                ref_image,
                provider_dd,
                model_dd,
                optimization_dd,
                optimized_for_state,
                use_description_cb,
                desc_method_dd,
                desc_verbosity_dd,
                think_cb,
                optimize_format_dd,
                lora_dd_0,
                lora_dd_1,
                lora_dd_2,
                lora_sl_0,
                lora_sl_1,
                lora_sl_2,
            ],
            outputs=_gen_outputs,
            concurrency_id=_UI_CONCURRENCY_ID,
        )
        gen_ev.then(js=_JS_SET_PAGE_TITLE, inputs=_gen_outputs, outputs=_gen_outputs)
        gen_ev.then(js=_JS_NOTIFY_IF_MSG, inputs=_gen_outputs, outputs=_gen_outputs)
        opt_ev = optimize_btn.click(
            fn=_optimize_click_handler,
            inputs=[
                prompt_tb,
                ref_image,
                optimization_dd,
                optimized_for_state,
                use_description_cb,
                desc_method_dd,
                desc_verbosity_dd,
                provider_dd,
                think_cb,
                optimize_format_dd,
            ],
            outputs=_opt_outputs,
            concurrency_id=_UI_CONCURRENCY_ID,
        )
        opt_ev.then(js=_JS_SET_PAGE_TITLE, inputs=_opt_outputs, outputs=_opt_outputs)
        opt_ev.then(js=_JS_NOTIFY_IF_MSG, inputs=_opt_outputs, outputs=_opt_outputs)
        _stop_outputs = [status_html, generate_btn, stop_btn, page_title]
        stop_btn.click(
            fn=_stop_click_handler,
            inputs=[],
            outputs=_stop_outputs,
            cancels=[gen_ev, opt_ev],
            concurrency_id=_UI_CONCURRENCY_ID,
        ).then(js=_JS_SET_PAGE_TITLE, inputs=_stop_outputs, outputs=_stop_outputs)

        prompt_tb.change(
            fn=_prompt_change_handler,
            inputs=[prompt_tb],
            outputs=[generate_btn, optimize_btn],
            concurrency_id=_UI_CONCURRENCY_ID,
        )

        optimize_cb.change(
            fn=_optimize_checkbox_handler,
            inputs=[optimize_cb],
            outputs=[optimized_tab],
        )

        gr.HTML(f"""
<div style="text-align: center; margin: 40px 0 20px 0; padding-top: 20px; border-top: 1px solid #e5e7eb;">
    <p style="
        font-size: 0.9em;
        color: #9ca3af;
        margin: 0 0 5px 0;
    ">genimg v{__version__}</p>
    <p style="
        font-size: 0.9em;
        color: #9ca3af;
        margin: 0;
    "><a href="https://github.com/codeprimate/genimg" target="_blank" style="
        color: #667eea;
        text-decoration: none;
        font-weight: 500;
        transition: color 0.2s;
    " onmouseover="this.style.color='#764ba2'" onmouseout="this.style.color='#667eea'">GitHub Repository ↗</a></p>
</div>
""")

        app.load(js=_JS_REQUEST_NOTIFICATION_PERMISSION)

    return cast(gr.Blocks, app)


def launch(
    server_name: str | None = None,
    server_port: int | None = None,
    share: bool = False,
) -> None:
    """
    Build the Gradio app and launch the server.

    Args:
        server_name: Host to bind (default: GENIMG_UI_HOST or 127.0.0.1).
        server_port: Port (default: GENIMG_UI_PORT or 7860).
        share: If True, create a public share link (e.g. gradio.live).
    """
    host = server_name or os.getenv("GENIMG_UI_HOST", DEFAULT_UI_HOST)
    port = server_port
    if port is None:
        try:
            port = int(os.getenv("GENIMG_UI_PORT", str(DEFAULT_UI_PORT)))
        except ValueError:
            port = DEFAULT_UI_PORT
    print(f"genimg ui is starting (v{__version__}) on http://{host}:{port}...")
    app = _build_blocks()
    favicon_path = _get_favicon_path()
    launch_kwargs: dict[str, Any] = {
        "server_name": host,
        "server_port": port,
        "share": share,
        "inbrowser": True,
    }
    if favicon_path:
        launch_kwargs["favicon_path"] = favicon_path
    app.launch(**launch_kwargs)


def main() -> None:
    """Entry point for the genimg-ui console script. Parses --port, --host, --share."""
    parser = argparse.ArgumentParser(
        description="Launch the genimg Gradio web UI for image generation.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help=f"Port to bind (default: GENIMG_UI_PORT or {DEFAULT_UI_PORT}).",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        metavar="HOST",
        help=f"Host to bind (default: GENIMG_UI_HOST or {DEFAULT_UI_HOST}). Use 0.0.0.0 for LAN.",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        default=None,
        help="Create a public share link (e.g. gradio.live). Overrides GENIMG_UI_SHARE.",
    )
    args = parser.parse_args()
    share_val = args.share
    if share_val is None:
        env_share = os.environ.get("GENIMG_UI_SHARE", "").lower()
        share_val = env_share in ("1", "true", "yes")
    launch(
        server_name=args.host,
        server_port=args.port,
        share=share_val,
    )
