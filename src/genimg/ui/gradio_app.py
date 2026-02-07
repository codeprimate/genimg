"""
Gradio web UI for genimg.

Single-page UI: prompt, optional optimization, optional reference image,
generate with progress and cancellation, view/download result (JPG 90, timestamp filename).
Uses only the public API: from genimg import ...
"""

import argparse
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


def _load_ui_models() -> tuple[list[str], str, list[str], str]:
    """
    Load image and optimization model lists from ui_models.yaml in the package.
    Returns (image_models, default_image_model, optimization_models, default_optimization_model).
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
    image_models: list[str] = data.get("image_models") or []
    default_image: str = data.get("default_image_model") or "bytedance-seed/seedream-4.5"
    opt_models: list[str] = data.get("optimization_models") or []
    default_opt: str = data.get("default_optimization_model") or "svjack/gpt-oss-20b-heretic"
    if default_opt and default_opt not in opt_models:
        opt_models = [default_opt] + [m for m in opt_models if m != default_opt]
    if default_image and default_image not in image_models:
        image_models = [default_image] + [m for m in image_models if m != default_image]
    return image_models, default_image, opt_models, default_opt


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
    return f"Done in {elapsed:.1f}s", str(out_path), f"Done in {elapsed:.1f}s"


def _run_generate_stream(
    prompt: str,
    optimize: bool,
    optimized_prompt_value: str | None,
    reference_value: Any,
    model: str | None,
    optimization_model: str | None = None,
    cancel_check: Any | None = None,
) -> Generator[tuple[str, str | None, bool, bool, str], None, None]:
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
    ref_b64: str | None = None
    ref_hash: str | None = None
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
                model=optimization_model,
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
    out_path = Path(tempfile.gettempdir()) / f"{ts}.jpg"
    result.image.save(str(out_path), "JPEG", quality=90)
    yield f"Done in {elapsed:.1f}s", str(out_path), True, False, box_value


def _generate_click_handler(
    p: str,
    opt: bool,
    opt_text: str,
    ref: Any,
    mod: str | None,
    opt_mod: str | None,
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
            optimization_model=opt_mod,
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


def _optimize_click_handler(
    p: str, ref: Any, opt_mod: str | None
) -> Generator[tuple[Any, ...], None, None]:
    """Optimize button logic: clear cancel, run stream, yield updates. Used by UI and tests."""
    _cancel_event.clear()
    try:
        for status_msg, opt_text, opt_on, stop_on, gen_on in _run_optimize_only_stream(
            p, ref, optimization_model=opt_mod, cancel_check=lambda: _cancel_event.is_set()
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


def _prompt_change_handler(text: str) -> tuple[Any, Any]:
    """Prompt change: enable Generate and Optimize when prompt is non-empty."""
    enabled = bool(text and text.strip())
    return gr.update(interactive=enabled), gr.update(interactive=enabled)


def _run_optimize_only_stream(
    prompt: str,
    reference_value: Any,
    optimization_model: str | None = None,
    cancel_check: Any | None = None,
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
    ref_hash: str | None = None
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
            model=optimization_model,
            reference_hash=ref_hash,
            enable_cache=False,  # Optimize button always forces a fresh run
            config=config,
            cancel_check=cancel_check,
        )
        yield "Optimized. Edit below if needed, then Generate.", optimized, True, False, True
    except (ValidationError, APIError, RequestTimeoutError, CancellationError) as e:
        yield _exception_to_message(e), "", True, False, True


def _build_blocks() -> gr.Blocks:
    """Build the Gradio Blocks UI (layout + generate handler, no cancellation yet)."""
    image_models, default_image, opt_models, default_opt = _load_ui_models()

    with gr.Blocks(title="genimg – AI image generation") as app:
        gr.Markdown("**AI image generation** with optional prompt optimization (Ollama).")

        with gr.Row():
            with gr.Column():
                prompt_tb = gr.Textbox(
                    label="Prompt",
                    placeholder="Describe the image you want to generate…",
                    lines=12,
                    max_lines=20,
                )
                optimize_cb = gr.Checkbox(
                    label="Optimize prompt with AI (Ollama)",
                    value=True,
                )
            with gr.Column():
                ref_image = gr.Image(
                    label="Reference image",
                    type="filepath",
                    sources=["upload", "clipboard"],
                )

        with gr.Row():
            generate_btn = gr.Button("Generate", variant="primary", interactive=False)
            stop_btn = gr.Button("Stop", interactive=False)
        model_dd = gr.Dropdown(
            label="Image model",
            value=default_image,
            choices=image_models,
            allow_custom_value=True,
            visible=True,
            info="OpenRouter image model. Type a model ID for another.",
        )
        optimization_dd = gr.Dropdown(
            label="Optimization model (Ollama)",
            value=default_opt,
            choices=opt_models,
            allow_custom_value=True,
            visible=True,
            info="Ollama model for prompt optimization.",
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
            inputs=[prompt_tb, optimize_cb, optimized_tb, ref_image, model_dd, optimization_dd],
            outputs=[status_tb, out_image, generate_btn, stop_btn, optimized_tb],
        )
        opt_ev = optimize_btn.click(
            fn=_optimize_click_handler,
            inputs=[prompt_tb, ref_image, optimization_dd],
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
    app = _build_blocks()
    app.launch(
        server_name=host,
        server_port=port,
        share=share,
    )


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
