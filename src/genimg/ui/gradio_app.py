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
import os
import tempfile
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

import gradio as gr
import yaml

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
    list_ollama_models,
    optimize_prompt,
    process_reference_image,
    validate_prompt,
)
from genimg.core.config import DEFAULT_IMAGE_MODEL
from genimg.core.image_analysis import (
    describe_image,
    get_description,
    unload_describe_models,
)
from genimg.core.providers import KNOWN_IMAGE_PROVIDERS
from genimg.logging_config import get_logger, log_prompts

logger = get_logger(__name__)

# Max prompt length for logging (large so prompts are effectively never truncated)
_UI_PROMPT_LOG_MAX = 50_000

# Default server port; overridable via GENIMG_UI_PORT
DEFAULT_UI_PORT = 7860
DEFAULT_UI_HOST = "127.0.0.1"

# Base page title (browser tab); status prefixes are prepended during optimize/generate
BASE_PAGE_TITLE = "genimg – AI image generation"


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


def _register_temp_path(path: str) -> None:
    _temp_paths.add(path)


def _cleanup_temp_paths() -> None:
    for path in _temp_paths:
        with contextlib.suppress(OSError):
            Path(path).unlink(missing_ok=True)


atexit.register(_cleanup_temp_paths)


def _initial_optimized_for_state() -> dict[str, Any]:
    """Initial value for optimized_for_state (JSON-serializable for Gradio)."""
    return {OPTIMIZED_FOR_PROMPT: "", OPTIMIZED_FOR_REF_HASH: None}


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


def _load_ui_models() -> tuple[list[str], list[str], str, str, str, list[str], str]:
    """
    Load image and optimization model lists from ui_models.yaml in the package.
    Returns (image_models, ollama_image_models, default_image_provider, default_image_model,
             default_ollama_model, optimization_models, default_optimization_model).
    """
    try:
        with (
            importlib.resources.files("genimg")
            .joinpath("ui_models.yaml")
            .open(encoding="utf-8") as f
        ):
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    # OpenRouter image models from YAML
    image_models: list[str] = data.get("image_models") or []
    default_image_yaml: str = data.get("default_image_model") or DEFAULT_IMAGE_MODEL
    if default_image_yaml and default_image_yaml not in image_models:
        image_models = [default_image_yaml] + [m for m in image_models if m != default_image_yaml]

    # Ollama image models from YAML or fallback (see https://ollama.com/blog/image-generation)
    ollama_image_models: list[str] = data.get("ollama_image_models") or [
        "x/z-image-turbo",  # Alibaba Tongyi Lab, photorealistic + bilingual text
        "x/flux2-klein",  # Black Forest Labs FLUX.2 Klein, 4B/9B
    ]
    default_ollama: str = data.get("default_ollama_image_model") or (
        ollama_image_models[0] if ollama_image_models else "x/z-image-turbo"
    )
    if default_ollama and default_ollama not in ollama_image_models:
        ollama_image_models = [default_ollama] + [
            m for m in ollama_image_models if m != default_ollama
        ]

    # Config: default provider and model for that provider
    config = Config.from_env()
    default_image_provider: str = config.default_image_provider
    default_image_model: str = (
        config.default_image_model if default_image_provider == "openrouter" else default_ollama
    )

    # Optimization models from installed Ollama models
    default_opt: str = config.default_optimization_model
    opt_models: list[str] = list_ollama_models()
    if default_opt and default_opt not in opt_models:
        opt_models = [default_opt] + opt_models
    elif default_opt and opt_models:
        opt_models = [default_opt] + [m for m in opt_models if m != default_opt]
    elif not opt_models:
        opt_models = [default_opt]

    return (
        image_models,
        ollama_image_models,
        default_image_provider,
        default_image_model,
        default_ollama,
        opt_models,
        default_opt,
    )


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
            _register_temp_path(path)
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
        result = generate_image(
            effective_prompt,
            model=model or None,
            reference_image_b64=ref_b64,
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
    _register_temp_path(str(out_path))
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
) -> Generator[tuple[str, str | None, bool, bool, str, dict[str, Any], str], None, None]:
    """
    Generate flow: use Optimized prompt box only when it was produced for the current
    (prompt, ref_hash); otherwise run optimize when checkbox on, else use Prompt.
    Yields (status, img_path, gen_on, stop_on, optimized_box_value, optimized_for_state, page_title).
    """
    state = optimized_for_state or _initial_optimized_for_state()
    # Value to show in Optimized prompt box; keep unchanged unless we run optimize
    box_value = (optimized_prompt_value or "").strip() or ""

    if not prompt or not prompt.strip():
        yield (
            _format_status("Enter a prompt to generate.", "warning"),
            None,
            True,
            False,
            box_value,
            state,
            BASE_PAGE_TITLE,
        )
        return
    logger.info("Generate requested")
    if log_prompts():
        truncated = (
            prompt if len(prompt) <= _UI_PROMPT_LOG_MAX else prompt[:_UI_PROMPT_LOG_MAX] + "..."
        )
        logger.info("Prompt: %s", truncated)
    config = Config.from_env()
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
            if provider == "ollama":
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
            )
            return
    ref_b64_to_send = ref_b64 if provider != "ollama" else None
    # Use optimized box only if it was produced for this exact (prompt, ref_hash)
    state_matches = (
        state.get(OPTIMIZED_FOR_PROMPT) == prompt and state.get(OPTIMIZED_FOR_REF_HASH) == ref_hash
    )
    if box_value and state_matches:
        effective_prompt = box_value
    elif box_value and not state_matches and optimize:
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
            state = {OPTIMIZED_FOR_PROMPT: prompt, OPTIMIZED_FOR_REF_HASH: ref_hash}
        except (ValidationError, APIError, RequestTimeoutError, CancellationError) as e:
            yield (
                _format_status(_exception_to_message(e), "error"),
                None,
                True,
                False,
                box_value,
                state,
                BASE_PAGE_TITLE,
            )
            return
    elif box_value and not state_matches and not optimize:
        # Stale box from different prompt; user has optimization off so use raw prompt
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
            state = {OPTIMIZED_FOR_PROMPT: prompt, OPTIMIZED_FOR_REF_HASH: ref_hash}
        except (ValidationError, APIError, RequestTimeoutError, CancellationError) as e:
            yield (
                _format_status(_exception_to_message(e), "error"),
                None,
                True,
                False,
                box_value,
                state,
                BASE_PAGE_TITLE,
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
    )
    try:
        result = generate_image(
            effective_prompt,
            model=model or None,
            reference_image_b64=ref_b64_to_send,
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
            box_value,
            state,
            BASE_PAGE_TITLE,
        )
        return
    elapsed = result.generation_time
    ts = int(time.time())
    out_path = Path(tempfile.gettempdir()) / f"{ts}.jpg"
    result.image.save(str(out_path), "JPEG", quality=90)
    _register_temp_path(str(out_path))
    yield (
        _format_status(f"Done in {elapsed:.1f}s", "success"),
        str(out_path),
        True,
        False,
        box_value,
        state,
        _page_title_with_status("[DONE]"),
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
) -> Generator[tuple[Any, ...], None, None]:
    """Generate button logic: clear cancel, run stream, yield updates. Used by UI and tests."""
    logger.debug("Generate clicked")
    _cancel_event.clear()
    state = optimized_for_state or _initial_optimized_for_state()
    ui_to_method = {"Prose (Florence)": "prose", "Tags (JoyTag)": "tags"}
    description_method = ui_to_method.get(desc_method_ui, "prose")
    try:
        for (
            status_msg,
            img_path,
            gen_on,
            stop_on,
            box_val,
            new_state,
            page_title,
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
) -> Generator[tuple[Any, ...], None, None]:
    """Optimize button logic: clear cancel, run stream, yield updates. Used by UI and tests."""
    logger.debug("Optimize clicked")
    _cancel_event.clear()
    state = optimized_for_state or _initial_optimized_for_state()
    ui_to_method = {"Prose (Florence)": "prose", "Tags (JoyTag)": "tags"}
    description_method = ui_to_method.get(desc_method_ui, "prose")
    try:
        for (
            status_msg,
            opt_text,
            opt_on,
            stop_on,
            gen_on,
            state_update,
            page_title,
        ) in _run_optimize_only_stream(
            p,
            ref,
            optimization_model=opt_mod,
            cancel_check=lambda: _cancel_event.is_set(),
            use_description=use_description,
            description_method=description_method,
            description_verbosity=desc_verbosity or "detailed",
            provider=provider,
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
) -> Generator[tuple[str, str, bool, bool, bool, dict[str, Any] | None, str], None, None]:
    """
    Run optimization only; yields (status_msg, optimized_text, optimize_btn_on, stop_btn_on, generate_btn_on, state_update, page_title).
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
        )
        return
    logger.info("Optimize requested")
    if log_prompts():
        truncated = (
            prompt if len(prompt) <= _UI_PROMPT_LOG_MAX else prompt[:_UI_PROMPT_LOG_MAX] + "..."
        )
        logger.info("Prompt: %s", truncated)
    config = Config.from_env()
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
            if provider == "ollama":
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
        state_update = {OPTIMIZED_FOR_PROMPT: prompt, OPTIMIZED_FOR_REF_HASH: ref_hash}
        yield (
            _format_status("Optimized. Edit above if needed, then Generate.", "success"),
            optimized,
            True,
            False,
            True,
            state_update,
            _page_title_with_status("[DONE]"),
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
    ) = _load_ui_models()

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
        <p style="font-size: 0.9em; color: #9ca3af; margin: 0; font-weight: 400;">Ollama prompt enhancement • Ollama/OpenRouter image models • Reference images for style transfer</p>
    </div>
</div>
"""

    with gr.Blocks(title=BASE_PAGE_TITLE) as app:
        gr.HTML(header_html)
        status_html = gr.HTML(value="", visible=True)
        page_title = gr.Textbox(value=BASE_PAGE_TITLE, visible=False, elem_id="genimg-page-title")

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
                            )
                            desc_verbosity_dd = gr.Dropdown(
                                label="Prose verbosity",
                                choices=["brief", "detailed", "more_detailed"],
                                value="detailed",
                                visible=True,
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
                    info="Use description in optimization; when provider is Ollama, ref image is not sent.",
                )

        with gr.Row():
            with gr.Column(scale=1):
                provider_dd = gr.Dropdown(
                    label="Image provider",
                    choices=list(KNOWN_IMAGE_PROVIDERS),
                    value=default_image_provider,
                    visible=True,
                )
            with gr.Column(scale=1):
                model_dd = gr.Dropdown(
                    label="Image model",
                    value=default_image_model,
                    choices=(
                        image_models
                        if default_image_provider == "openrouter"
                        else ollama_image_models
                    ),
                    allow_custom_value=True,
                    visible=True,
                    info="Model for the selected provider. Type a model ID for another.",
                )
                ref_message = gr.HTML(
                    value=_format_status(_REF_NOT_SUPPORTED_MSG, "warning"),
                    visible=(default_image_provider == "ollama"),
                )

        def _on_provider_change(provider: str) -> tuple[Any, Any]:
            if provider == "ollama":
                return (
                    gr.update(choices=ollama_image_models, value=default_ollama),
                    gr.update(
                        visible=True,
                        value=_format_status(_REF_NOT_SUPPORTED_MSG, "warning"),
                    ),
                )
            config = Config.from_env()
            openrouter_default = config.default_image_model or (
                image_models[0] if image_models else "bytedance-seed/seedream-4.5"
            )
            return (
                gr.update(choices=image_models, value=openrouter_default),
                gr.update(visible=False),
            )

        provider_dd.change(
            fn=_on_provider_change,
            inputs=[provider_dd],
            outputs=[model_dd, ref_message],
        )

        def _on_desc_method_change(method: str) -> Any:
            return gr.update(visible=(method == "Prose (Florence)"))

        desc_method_dd.change(
            fn=_on_desc_method_change,
            inputs=[desc_method_dd],
            outputs=[desc_verbosity_dd],
        )

        def _ref_image_change(ref_value: Any) -> Any:
            src = _reference_source_for_process(ref_value)
            return gr.update(interactive=(src is not None))

        ref_image.change(
            fn=_ref_image_change,
            inputs=[ref_image],
            outputs=[describe_btn],
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
        _gen_outputs = [
            status_html,
            out_image,
            generate_btn,
            stop_btn,
            optimized_tb,
            optimized_for_state,
            page_title,
        ]
        _opt_outputs = [
            status_html,
            optimized_tb,
            optimize_btn,
            stop_btn,
            generate_btn,
            optimized_for_state,
            page_title,
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
            ],
            outputs=_gen_outputs,
            concurrency_id=_UI_CONCURRENCY_ID,
        )
        gen_ev.then(js=_JS_SET_PAGE_TITLE, inputs=_gen_outputs, outputs=_gen_outputs)
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
            ],
            outputs=_opt_outputs,
            concurrency_id=_UI_CONCURRENCY_ID,
        )
        opt_ev.then(js=_JS_SET_PAGE_TITLE, inputs=_opt_outputs, outputs=_opt_outputs)
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
