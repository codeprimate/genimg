"""
Gradio web UI for genimg.

Single-page UI: prompt, optional optimization, optional reference image,
generate with progress and cancellation, view/download result (JPG 90, timestamp filename).
Uses only the public API: from genimg import ...
"""

import os
import tempfile
import threading
import time
from typing import Any, Generator, Optional

import gradio as gr

from genimg import (
    APIError,
    CancellationError,
    ConfigurationError,
    Config,
    GenimgError,
    ImageProcessingError,
    NetworkError,
    RequestTimeoutError,
    ValidationError,
    generate_image,
    optimize_prompt,
    process_reference_image,
    validate_prompt,
)

# Default server port; overridable via GENIMG_UI_PORT
DEFAULT_UI_PORT = 7860
DEFAULT_UI_HOST = "127.0.0.1"

# Shared cancellation event: Generate clears at start, Stop sets it
_cancel_event = threading.Event()


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


def _reference_source_for_process(value: Any) -> Optional[Any]:
    """
    Get a source suitable for process_reference_image from Gradio Image value.

    With type='filepath', Gradio passes a path str. We also support None and dict with 'path'.
    """
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, dict):
        path = value.get("path") or value.get("url")
        if path and isinstance(path, str):
            return path
        return None
    return value  # str path or Path


def _run_generate(
    prompt: str,
    optimize: bool,
    reference_value: Any,
    model: Optional[str],
    cancel_check: Optional[Any] = None,
) -> tuple[Optional[str], Optional[Any], str]:
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

    ref_b64: Optional[str] = None
    ref_hash: Optional[str] = None
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
    out_path = os.path.join(tempfile.gettempdir(), f"{ts}.jpg")
    result.image.save(out_path, "JPEG", quality=90)
    return f"Done in {elapsed:.1f}s", out_path, f"Done in {elapsed:.1f}s"


def _run_generate_stream(
    prompt: str,
    optimize: bool,
    optimized_prompt_value: Optional[str],
    reference_value: Any,
    model: Optional[str],
    cancel_check: Optional[Any] = None,
) -> Generator[tuple[str, Optional[str], bool, bool, str], None, None]:
    """
    Generate flow: use Optimized prompt box if non-empty (edit-then-generate), else run
    optimize when checkbox on, else use Prompt. Yields (status, img_path, gen_on, stop_on, optimized_box_value).
    """
    # Value to show in Optimized prompt box; keep unchanged unless we run optimize
    box_value = (optimized_prompt_value or "").strip() or ""

    if not prompt or not prompt.strip():
        yield "Enter a prompt to generate.", None, True, False, box_value
        return
    config = Config.from_env()
    try:
        config.validate()
    except ConfigurationError as e:
        yield _exception_to_message(e), None, True, False, box_value
        return
    try:
        validate_prompt(prompt)
    except ValidationError as e:
        yield _exception_to_message(e), None, True, False, box_value
        return
    ref_b64: Optional[str] = None
    ref_hash: Optional[str] = None
    ref_source = _reference_source_for_process(reference_value)
    if ref_source is not None:
        try:
            ref_b64, ref_hash = process_reference_image(ref_source, config=config)
        except (ValidationError, ImageProcessingError, FileNotFoundError) as e:
            yield _exception_to_message(e), None, True, False, box_value
            return
    # Use edited optimized prompt if present; otherwise optimize when checkbox on
    if box_value:
        effective_prompt = box_value
    elif optimize:
        config.optimization_enabled = True
        yield "Optimizing…", None, False, True, box_value
        try:
            effective_prompt = optimize_prompt(
                prompt,
                reference_hash=ref_hash,
                config=config,
                cancel_check=cancel_check,
            )
            box_value = effective_prompt
        except (ValidationError, APIError, RequestTimeoutError, CancellationError) as e:
            yield _exception_to_message(e), None, True, False, box_value
            return
    else:
        effective_prompt = prompt
    yield "Generating…", None, False, True, box_value
    try:
        result = generate_image(
            effective_prompt,
            model=model or None,
            reference_image_b64=ref_b64,
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
        yield _exception_to_message(e), None, True, False, box_value
        return
    elapsed = result.generation_time
    ts = int(time.time())
    out_path = os.path.join(tempfile.gettempdir(), f"{ts}.jpg")
    result.image.save(out_path, "JPEG", quality=90)
    yield f"Done in {elapsed:.1f}s", out_path, True, False, box_value


def _generate_click_handler(
    p: str,
    opt: bool,
    opt_text: str,
    ref: Any,
    mod: Optional[str],
) -> Generator[tuple[Any, ...], None, None]:
    """Generate button logic: clear cancel, run stream, yield updates. Used by UI and tests."""
    _cancel_event.clear()
    try:
        for status_msg, img_path, gen_on, stop_on, box_val in _run_generate_stream(
            p,
            opt,
            opt_text,
            ref,
            mod,
            cancel_check=lambda: _cancel_event.is_set(),
        ):
            yield (
                status_msg,
                img_path,
                gr.update(interactive=gen_on),
                gr.update(interactive=stop_on),
                box_val,
            )
    except GenimgError as e:
        yield (
            _exception_to_message(e),
            None,
            gr.update(interactive=True),
            gr.update(interactive=False),
            opt_text,
        )
    except Exception as e:
        yield (
            str(e),
            None,
            gr.update(interactive=True),
            gr.update(interactive=False),
            opt_text,
        )


def _optimize_click_handler(p: str, ref: Any) -> Generator[tuple[Any, ...], None, None]:
    """Optimize button logic: clear cancel, run stream, yield updates. Used by UI and tests."""
    _cancel_event.clear()
    try:
        for status_msg, opt_text, opt_on, stop_on, gen_on in _run_optimize_only_stream(
            p, ref, cancel_check=lambda: _cancel_event.is_set()
        ):
            yield (
                status_msg,
                opt_text,
                gr.update(interactive=opt_on),
                gr.update(interactive=stop_on),
                gr.update(interactive=gen_on),
            )
    except GenimgError as e:
        yield (
            _exception_to_message(e),
            "",
            gr.update(interactive=True),
            gr.update(interactive=False),
            gr.update(interactive=True),
        )
    except Exception as e:
        yield (
            str(e),
            "",
            gr.update(interactive=True),
            gr.update(interactive=False),
            gr.update(interactive=True),
        )


def _stop_click_handler() -> tuple[Any, Any]:
    """Stop button logic: set cancel event, restore button states."""
    _cancel_event.set()
    return gr.update(interactive=True), gr.update(interactive=False)


def _prompt_change_handler(text: str) -> tuple[gr.update, gr.update]:
    """Prompt change: enable Generate and Optimize when prompt is non-empty."""
    enabled = bool(text and text.strip())
    return gr.update(interactive=enabled), gr.update(interactive=enabled)


def _run_optimize_only_stream(
    prompt: str,
    reference_value: Any,
    cancel_check: Optional[Any] = None,
) -> Generator[tuple[str, str, bool, bool, bool], None, None]:
    """
    Run optimization only; yields (status_msg, optimized_text, optimize_btn_on, stop_btn_on, generate_btn_on).
    Used for Optimize / Regenerate button.
    """
    prompt_ok = bool(prompt and prompt.strip())
    if not prompt_ok:
        yield "Enter a prompt to optimize.", "", True, False, False
        return
    config = Config.from_env()
    try:
        config.validate()
    except ConfigurationError as e:
        yield _exception_to_message(e), "", True, False, True
        return
    try:
        validate_prompt(prompt)
    except ValidationError as e:
        yield _exception_to_message(e), "", True, False, True
        return
    ref_hash: Optional[str] = None
    ref_source = _reference_source_for_process(reference_value)
    if ref_source is not None:
        try:
            _, ref_hash = process_reference_image(ref_source, config=config)
        except (ValidationError, ImageProcessingError, FileNotFoundError) as e:
            yield _exception_to_message(e), "", True, False, True
            return
    config.optimization_enabled = True
    yield "Optimizing…", "", False, True, False
    try:
        optimized = optimize_prompt(
            prompt,
            reference_hash=ref_hash,
            config=config,
            cancel_check=cancel_check,
        )
        yield "Optimized. Edit below if needed, then Generate.", optimized, True, False, True
    except (ValidationError, APIError, RequestTimeoutError, CancellationError) as e:
        yield _exception_to_message(e), "", True, False, True


def _build_blocks() -> gr.Blocks:
    """Build the Gradio Blocks UI (layout + generate handler, no cancellation yet)."""
    with gr.Blocks(title="genimg – AI image generation") as app:
        gr.Markdown(
            "**AI image generation** with optional prompt optimization (Ollama)."
        )

        with gr.Row():
            prompt_tb = gr.Textbox(
                label="Prompt",
                placeholder="Describe the image you want to generate…",
                lines=4,
                max_lines=8,
            )
        with gr.Row():
            generate_btn = gr.Button("Generate", variant="primary", interactive=False)
            stop_btn = gr.Button("Stop", interactive=False)
        with gr.Row():
            optimize_cb = gr.Checkbox(
                label="Optimize prompt with AI (Ollama)",
                value=True,
            )
            ref_image = gr.Image(
                label="Reference image",
                type="filepath",
                sources=["upload", "clipboard"],
            )
            model_dd = gr.Dropdown(
                label="Model",
                value=None,
                choices=[],
                allow_custom_value=False,
                visible=False,
            )
        optimized_tb = gr.Textbox(
            label="Optimized prompt (editable)",
            placeholder="Click Optimize or run Generate with 'Optimize prompt' checked to fill. Edit then Generate.",
            lines=3,
            max_lines=6,
        )
        with gr.Row():
            optimize_btn = gr.Button("Optimize", variant="secondary", interactive=False)
        status_tb = gr.Textbox(
            label="Status",
            value="",
            interactive=False,
        )
        out_image = gr.Image(label="Output", type="filepath")

        gen_ev = generate_btn.click(
            fn=_generate_click_handler,
            inputs=[prompt_tb, optimize_cb, optimized_tb, ref_image, model_dd],
            outputs=[status_tb, out_image, generate_btn, stop_btn, optimized_tb],
        )
        opt_ev = optimize_btn.click(
            fn=_optimize_click_handler,
            inputs=[prompt_tb, ref_image],
            outputs=[status_tb, optimized_tb, optimize_btn, stop_btn, generate_btn],
        )
        stop_btn.click(
            fn=_stop_click_handler,
            inputs=[],
            outputs=[generate_btn, stop_btn],
            cancels=[gen_ev, opt_ev],
        )

        prompt_tb.change(
            fn=_prompt_change_handler,
            inputs=[prompt_tb],
            outputs=[generate_btn, optimize_btn],
        )

    return app


def launch(
    server_name: Optional[str] = None,
    server_port: Optional[int] = None,
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
    app = _build_blocks()
    app.launch(
        server_name=host,
        server_port=port,
        share=share,
    )
