# Architecture Decision Records (ADRs)

This document tracks significant technical decisions made during the development of genimg.

## Format

Each decision record includes:
- **Date**: When the decision was made
- **Decision**: What was decided
- **Context**: The problem we were solving
- **Options Considered**: Alternatives that were evaluated
- **Rationale**: Why this choice was made
- **Consequences**: Trade-offs and implications

---

## ADR-001: Use src/ Layout for Package Structure

**Date**: 2026-02-06

**Decision**: Use the src/ layout where the package lives in `src/genimg/` rather than flat layout with `genimg/` at the project root.

**Context**: Need to decide on package structure that works well with modern Python tooling and prevents common import issues.

**Options Considered**:
1. Flat layout (`genimg/` at root)
2. src/ layout (`src/genimg/`)

**Rationale**:
- src/ layout prevents accidental imports of development code
- Better isolation between installed package and source
- Recommended by modern Python packaging guides (PEP 517/518)
- Works better with editable installs

**Consequences**:
- Import paths are `from genimg.core import ...`
- Must use `pip install -e .` for development
- Slightly more directory nesting

---

## ADR-002: Use Click for CLI Framework

**Date**: 2026-02-06

**Decision**: Use Click for the command-line interface instead of Typer or argparse.

**Context**: Need a CLI framework that's mature, well-documented, and provides good UX.

**Options Considered**:
1. **Click**: Decorator-based, mature, widely used
2. **Typer**: Modern, type-hint based, built on Click
3. **argparse**: Standard library

**Rationale**:
- Click is mature and battle-tested
- Excellent documentation and community support
- Decorator syntax is clear and concise
- Good integration with setuptools entry points
- Typer adds complexity we don't need yet

**Consequences**:
- CLI uses decorator pattern: `@click.command()`
- No automatic type validation from hints (must validate manually)
- Well-established patterns for error handling

---

## ADR-003: Use Ollama Locally for Prompt Optimization

**Date**: 2026-02-06

**Decision**: Use Ollama running locally via subprocess for prompt optimization rather than cloud APIs.

**Context**: Need to optimize user prompts to improve image generation results. Must decide between local and cloud solutions.

**Options Considered**:
1. **Ollama locally**: Subprocess calls to local Ollama
2. **OpenRouter LLMs**: Use same API for optimization
3. **OpenAI API**: Direct API calls

**Rationale**:
- Local = no additional API costs
- Ollama is free and easy to install
- Works offline once models are downloaded
- User has full control and privacy
- Prompt optimization is optional feature

**Consequences**:
- Requires users to install Ollama separately
- Optimization feature optional (not all users will have it)
- Must handle subprocess management (timeout, cancellation)
- Cannot stream responses easily
- Performance depends on user's hardware

---

## ADR-004: In-Memory Cache for Optimized Prompts

**Date**: 2026-02-06

**Decision**: Use in-memory session-scoped cache for optimized prompts rather than persistent storage.

**Context**: Avoid redundant Ollama calls when same prompt is optimized multiple times in a session.

**Options Considered**:
1. **In-memory only**: Python dict, session-scoped
2. **Disk cache**: SQLite or file-based
3. **No caching**: Always re-optimize

**Rationale**:
- Simple implementation
- No file I/O overhead
- No stale data issues
- Sessions are typically short
- Optimization is relatively fast (~5-30s)
- Disk cache adds complexity for marginal benefit

**Consequences**:
- Cache cleared when app restarts
- Memory usage grows with unique prompts (bounded by session length)
- No persistence between sessions
- Simple to implement and debug

---

## ADR-005: Use OpenRouter for Image Generation

**Date**: 2026-02-06

**Decision**: Use OpenRouter as the image generation API provider.

**Context**: Need access to multiple image generation models without implementing separate integrations for each.

**Options Considered**:
1. **OpenRouter**: Unified API for multiple models
2. **Direct provider APIs**: Separate integrations for each model
3. **Replicate**: Alternative aggregator

**Rationale**:
- Single API for multiple models
- Consistent pricing and billing
- Good documentation
- Supports multimodal inputs (text + image)
- Free tier available for testing

**Consequences**:
- Dependent on OpenRouter's availability
- Limited to models OpenRouter supports
- Must handle OpenRouter's specific response format
- Users need OpenRouter API key

---

## ADR-006: Resize Reference Images to 2MP

**Date**: 2026-02-06

**Decision**: Automatically resize reference images to 2 megapixels while maintaining aspect ratio.

**Context**: Large images can exceed API payload limits and increase costs.

**Options Considered**:
1. **Fixed dimension**: Resize to 1024x1024
2. **Fixed pixel count**: Resize to 2MP maintaining aspect ratio
3. **No resize**: Let API handle it

**Rationale**:
- 2MP is reasonable quality for reference
- Maintains aspect ratio (better than fixed dimensions)
- Reduces API payload size
- Prevents timeout issues with large images
- Still allows high-quality reference images

**Consequences**:
- All reference images are resized
- Original aspect ratio preserved
- May reduce quality of very detailed references
- Consistent behavior across all image sizes

---

## ADR-007: Use Gradio for Web UI

**Date**: 2026-02-06

**Decision**: Use Gradio for the web interface rather than building custom web app.

**Context**: Need a web UI for users who prefer graphical interface over CLI.

**Options Considered**:
1. **Gradio**: ML-focused UI framework
2. **Streamlit**: Similar rapid development framework
3. **Flask/FastAPI**: Custom web app

**Rationale**:
- Gradio is designed for ML applications
- Very fast development
- Built-in file upload, image display
- Good for rapid prototyping
- Easy to deploy

**Consequences**:
- Limited customization compared to custom web app
- Gradio-specific UI patterns
- Depends on Gradio's update cycle
- Good enough for MVP

---

## ADR-008: Type Hints Throughout

**Date**: 2026-02-06

**Decision**: Use type hints on all functions and enforce with mypy in strict mode.

**Context**: Want to improve code quality and IDE support.

**Options Considered**:
1. **Full type hints + mypy strict**
2. **Partial type hints**
3. **No type hints**

**Rationale**:
- Better IDE autocomplete and error detection
- Catch bugs before runtime
- Self-documenting code
- Modern Python best practice
- Small upfront cost for long-term benefit

**Consequences**:
- Must add type hints to all new code
- mypy checks as part of CI
- Some external libraries need type stubs
- Slightly more verbose code

---

## ADR-009: Custom Exception Hierarchy

**Date**: 2026-02-06

**Decision**: Create custom exception hierarchy with specific exception types for different error categories.

**Context**: Need clear error handling and user-friendly error messages.

**Options Considered**:
1. **Custom exception hierarchy**
2. **Standard exceptions only**
3. **String error codes**

**Rationale**:
- Clear error categories
- Can attach metadata (status_code, field_name, etc.)
- Easy to catch specific error types
- User-friendly messages
- Better error handling in UI/CLI

**Consequences**:
- More exception classes to maintain
- Clear error handling patterns
- Easy to provide helpful error messages
- Testable error conditions

---

## ADR-010: Cancellation via cancel_check Callable

**Date**: 2026-02-07

**Decision**: Support cancellation of long-running operations (prompt optimization, image generation) by accepting an optional `cancel_check: Optional[Callable[[], bool]]` on the public entry points. When provided, the library runs the blocking work in a daemon thread and polls `cancel_check()` on the calling thread; if it returns True, the library raises `CancellationError` and (for Ollama) terminates the subprocess.

**Context**: LIBRARY_SPEC requires cancellation "when supported." Optimization (Ollama) and generation (OpenRouter) can run for many seconds; users must be able to interrupt.

**Options Considered**:
1. **cancel_check callable**: Caller passes a function returning True to cancel; library polls from the main thread. No new types; works with threading.Event (e.g. `lambda: event.is_set()`).
2. **threading.Event only**: Library creates an event and returns it; caller sets it to cancel. Ties the API to threading.
3. **Defer cancellation**: Rely on process SIGINT only. Rejected because cancellation was deemed critical.

**Rationale**:
- cancel_check is interface-agnostic and testable; caller can use an Event, a flag, or CLI SIGINT handler that sets a flag.
- For Ollama we can actually terminate the subprocess, so resources are released.
- For OpenRouter we stop waiting and raise; the HTTP request may complete in the background (requests has no synchronous abort). Acceptable.

**Consequences**:
- `optimize_prompt`, `optimize_prompt_with_ollama`, and `generate_image` accept optional `cancel_check`. When None, behavior is unchanged (no thread).
- CLI/UI can pass e.g. `cancel_check=lambda: cancel_event.is_set()` and set the event on Ctrl+C.
- Two unit tests cover cancellation (prompt and image_gen).

**Best practices and practical concerns**:
- **cancel_check contract**: Callable should return quickly and not raise; the library catches exceptions from cancel_check and ignores them so a buggy callback does not abort the operation.
- **Poll interval**: 0.25s. Spec asks for cancellation acknowledged within 100ms; worst case is one poll period (250ms). Can be reduced to 0.1s if stricter latency is needed.
- **Daemon threads**: Workers are daemon threads so process exit is not blocked if the main thread exits (e.g. after raising CancellationError).
- **Ollama**: On cancel we call `process.terminate()` then `thread.join(timeout=5)`. The subprocess is actually stopped; no lingering work.
- **OpenRouter**: We only stop waiting and raise; the HTTP request continues in the worker until it completes. No way to abort a synchronous `requests` call from another thread. Thread exits when the request finishes; daemon=True prevents blocking process exit.
- **Thread accumulation**: Repeated cancel-and-retry can leave a few short-lived worker threads (one per cancelled generation) until their requests complete. Acceptable for CLI; for long-lived servers, document or consider a thread pool if needed.
- **Python 3.10+**: Built-in `tuple[str, str]` etc. are fine; no need for `typing.Tuple` for return types.

---

## ADR-009: Python 3.10+ and Gradio 6.x for Web UI

**Date**: 2026-02-07

**Decision**: Require Python >=3.10 for the project and use Gradio 6.x for the web UI so implementation follows the latest supported Gradio APIs.

**Context**: Gradio is the chosen web UI framework (ADR-007). Latest stable Gradio (6.x) requires Python 3.10+; Gradio dropped 3.8/3.9 support. We want to use the latest Gradio supported on our Python version to establish correct patterns and avoid outdated APIs.

**Options Considered**:
1. **Upgrade to Python 3.10 + Gradio 6.x**: Use latest Gradio and bump project requires-python.
2. **Keep Python 3.8 + pin Gradio 4.x**: Stay on older Gradio that supports 3.8; miss 6.x features and patterns.
3. **Support both**: Multiple CI legs and dependency matrix; rejected for complexity.

**Rationale**:
- Gradio 6 is the current stable; 4.x is legacy. New UI code should follow Gradio 6 patterns (Blocks, events, cancellation).
- Python 3.8 is EOL (Oct 2024); 3.10+ is a reasonable minimum for new work.
- Single Python/Gradio baseline keeps implementation and docs consistent.

**Consequences**:
- `requires-python = ">=3.10"` in pyproject.toml; classifiers and tool configs (black, ruff, mypy) target 3.10.
- Dependency: `gradio>=6.0.0,<7` (or pinned 6.x). Implementation and GRADIO_UI_PLAN must reference Gradio 6 docs.
- Contributors and users must have Python 3.10+.

---

## ADR-010: GenerationResult returns PIL Image as primary output

**Date**: 2026-02-07

**Decision**: The library returns a PIL (Pillow) Image as the primary output of image generation. `GenerationResult` has an `image` attribute (PIL `Image.Image`); `image_data` and `format` remain as derived properties for backward compatibility.

**Context**: Callers (CLI, UI, scripts) need to save, convert format, or get bytes. A PIL object lets each caller do what they need (e.g. save as JPEG at quality 90, or write raw bytes) without the library encoding output format or filename.

**Options Considered**:
1. **Return PIL Image**: Primary output is `result.image`; keep `image_data`/`format` as properties for compat.
2. **Return only bytes**: Caller would need to decode to PIL for conversion; duplicates logic.
3. **Return bytes + separate conversion helpers**: More API surface; PIL is standard for image handling in Python.

**Rationale**:
- PIL is already a dependency (reference image handling). One decode in the library; callers use the object as needed.
- CLI and UI can use `result.image.save(path, "JPEG", quality=90)` or `result.image_data` for simple write.
- Backward compatibility: existing code using `result.image_data` and `result.format` continues to work.

**Consequences**:
- `GenerationResult.image` is the primary attribute; `image_data` and `format` are properties derived from it.
- Documentation (LIBRARY_SPEC, SPEC, README, EXAMPLES) updated to describe PIL as primary and image_data/format as compat.

---

## ADR-011: Pluggable image generation providers

**Date**: 2026-02-16

**Decision**: Support multiple image generation providers (e.g. OpenRouter, Ollama) behind a common interface. Use a global provider registry; CLI accepts `--provider`; Gradio UI lets the user choose provider and loads models per provider.

**Context**: OpenRouter was the initial provider (ADR-005). Users and use cases benefit from also supporting Ollama (local, no API key). We need a single code path that can switch providers without duplicating UI/CLI logic.

**Options Considered**:
1. **Provider abstraction + registry**: Base `ImageGenerationProvider` interface; registry maps id → implementation; core/image_gen delegates to selected provider.
2. **Single provider, config switch**: Keep one implementation, branch internally by config. Rejected: would bloat one module and make adding providers hard.
3. **Separate tools per provider**: Different commands or UIs per provider. Rejected: fragments UX and maintenance.

**Rationale**:
- Registry keeps core agnostic of concrete providers; new providers (e.g. Replicate) can be added by implementing the interface and registering.
- CLI `--provider` and UI dropdown give explicit control; default provider comes from config.
- Reference-image compatibility can be validated per provider (e.g. Ollama vs OpenRouter capabilities).

**Consequences**:
- `genimg.core.providers` holds base, registry, and provider implementations (e.g. `ollama`, `openrouter`).
- Config includes default image provider and provider-specific settings (e.g. Ollama base URL).
- Gradio model dropdown and API calls depend on selected provider; tests cover provider selection and validation.

---

## ADR-012: Browser notifications for completion in Gradio

**Date**: 2026-02-24

**Decision**: Use the browser Notification API to notify users when image generation or prompt optimization completes, so they get feedback even if the tab is in the background. Permission is requested on app load; a hidden Gradio component carries the notification message; client-side JS in `.then(js=...)` shows the notification and clears the message.

**Context**: Generate and optimize can take many seconds. Users may switch tabs; without feedback they may not notice completion or errors.

**Options Considered**:
1. **Browser Notification API**: Standard, OS-level notifications; requires permission. Implemented.
2. **Sound only**: Simpler but less visible and no message text.
3. **No notification**: Rely on tab title or user staying on tab. Rejected for long-running ops.

**Rationale**:
- Notifications are optional (user can deny permission). We only notify on terminal outcomes (success or error) for generate and optimize; we skip description (fast), stop, and validation warnings to avoid noise.
- Single hidden `gr.Textbox` for the message keeps the Python API simple; `.then(js=...)` runs in the browser so we can call `new Notification(...)` and clear the payload to avoid duplicate notifications on later events.
- Documented in `docs/browser-notifications.md` with architecture and sequence.

**Consequences**:
- On load, app requests `Notification.requestPermission()`. If granted, generate/optimize completion (and errors) set a notify message that JS turns into a system notification.
- No notification when the user cancels (CancellationError); we do not notify for description or stop.
- Behavior depends on browser support and user permission; degrades gracefully if denied or unsupported.

---

## ADR-013: Temporary file lifecycle in Gradio UI

**Date**: 2026-02-16

**Decision**: The Gradio UI creates temporary files for reference images and generated output so components can display them. Track all temp paths in module-level sets; treat “image” paths (ref and output) as a subset cleaned on each Generate click; clean all temp paths at process exit via `atexit`.

**Context**: Gradio often needs file paths or URLs to show images. We must write generated PIL images and sometimes reference inputs to temp files. Without a clear lifecycle, temp dirs can accumulate and leak disk space.

**Options Considered**:
1. **Register paths + cleanup on Generate + atexit**: One set for all temp paths, one for image paths; clear image paths when user clicks Generate (new run), clear all on exit. Chosen.
2. **Cleanup only on exit**: Simpler but more files accumulate between runs in a long-lived server.
3. **In-memory only**: Use data URLs or in-memory streams everywhere. Gradio support and compatibility vary; some flows need paths. Rejected for current implementation.

**Rationale**:
- Cleaning image paths on each Generate keeps the “current run” bounded (one set of refs + one output); previous run’s images are discarded. All temp paths (including favicon copy, etc.) are still removed on exit.
- atexit ensures cleanup even if the server exits abnormally. Module-level sets are acceptable because the app is single-process.

**Consequences**:
- Helpers: `_register_temp_path`, `_register_temp_image_path`, `_cleanup_temp_images` (on Generate), `_cleanup_temp_paths` (atexit). Favicon and reference images use a temp copy when needed; generated output is written to a timestamped file in `tempfile.gettempdir()` and registered as an image path.
- Later enhancements (e.g. 0.10.1) can refine when and how paths are cleared; the principle of “track, clear images on new run, clear all on exit” remains.

---

## ADR-014: Structured logging and verbosity

**Date**: 2026-02-07

**Decision**: Use a single structured logging scheme with three verbosity levels (0=default, 1=info, 2=verbose). Level 0 logs activity and performance only; level 1 adds prompt text (original/optimized); level 2 sets DEBUG and adds API/cache detail (no secrets). Control via `set_verbosity(level)` or `configure_logging(verbose_level, quiet)` in the library; `GENIMG_VERBOSITY` env (0/1/2) for library and UI; CLI `-v`/`-vv` and `--quiet` override env. Logging is configured lazily so unconfigured library use produces no logs.

**Context**: We need consistent, controllable logging across CLI, library, and Gradio UI without spamming users or leaking prompts/secrets in default use.

**Options Considered**:
1. **Three levels + env + CLI override**: Chosen. Single mechanism; UI respects env; scripts can use `--quiet`.
2. **Single level or binary verbose**: Too coarse; we want to separate "prompts" from "API debug".
3. **Per-module levels**: More flexible but more complexity; not needed for current scope.

**Rationale**:
- Default (0) is safe for shared environments and logs; -v helps users see what prompt was sent; -vv helps diagnose API/cache issues.
- Lazy configuration avoids importing logging side effects when the library is used without logging.
- `--quiet` (WARNING only) suits scripts and CI where only failures should appear.

**Consequences**:
- `genimg.logging_config`: `set_verbosity`, `configure_logging`, `get_verbosity_from_env`, `log_prompts()` for conditional prompt logging.
- CLI applies verbosity from flags or env before running commands; UI calls `configure_logging(verbose_level=get_verbosity_from_env())` on startup.
- No secrets in logs; debug_api can truncate image data in payload/response logs.

---

## ADR-015: Reference image resize with configurable aspect ratio and bounds

**Date**: 2026-02-09

**Decision**: Generalize reference image processing beyond a fixed 2MP cap: support configurable `max_image_pixels`, `min_image_pixels`, and `aspect_ratio` (width, height) in config. Resize to fit within `max_image_pixels` while preserving aspect ratio, then pad to match `aspect_ratio` (default 1:1). Reject images that would fall below `min_image_pixels` with `ValidationError`. Validate config at load (min &lt;= max, aspect_ratio components positive).

**Context**: ADR-006 fixed 2MP and aspect-ratio preservation. Different APIs or use cases need different target aspect ratios or bounds; very small images are useless as references.

**Options Considered**:
1. **Configurable max, min, aspect_ratio**: Chosen. Single code path; config and env (e.g. GENIMG_MIN_IMAGE_PIXELS) drive behavior.
2. **Keep 2MP only**: Too rigid for multi-provider and future APIs.
3. **Per-provider resize config**: Possible future extension; for now one global config is enough.

**Rationale**:
- Pad-to-aspect-ratio gives consistent input shape for models that expect it; configurable ratio allows 16:9, 1:1, etc. without code changes.
- min_pixels avoids sending tiny images that waste API calls or produce poor results.
- Config validation at startup fails fast with clear errors.

**Consequences**:
- `Config`: `min_image_pixels`, `max_image_pixels`, `aspect_ratio`; `validate()` enforces ordering and positive components.
- `reference.resize_image()` and `prepare_reference_image()` use config when arguments are omitted; callers can override for tests.
- GENIMG_MIN_IMAGE_PIXELS (and future env for max/aspect) allow tuning without code change.

---

## ADR-016: Prompt normalization in Gradio UI

**Date**: 2026-02-24

**Decision**: In the Gradio UI, normalize the prompt string (strip leading/trailing whitespace) before storing in state and before comparing "current prompt" to "optimized for" prompt. Use a single helper `_normalize_prompt(s)` so all comparisons and state updates are consistent.

**Context**: Users may paste prompts with trailing newlines or spaces. If we compare raw strings, "foo" and "foo " would be treated as different and we would re-enable Optimize or overwrite state incorrectly.

**Options Considered**:
1. **Strip whitespace for state and comparison**: Chosen. Simple; avoids spurious re-optimize and keeps "optimized for" matching user-visible prompt.
2. **No normalization**: Comparison and state would be brittle.
3. **Full Unicode normalize or collapse internal space**: Overkill for current needs; strip is enough.

**Rationale**:
- "Optimization condition" (whether to show Optimize as already done) is based on normalized prompt equality. Normalization ensures we don't ask users to re-optimize when the only difference is whitespace.
- State (e.g. OPTIMIZED_FOR_PROMPT) stores normalized value so round-trips are consistent.

**Consequences**:
- All reads of prompt for comparison or state use `_normalize_prompt(...)`. Display can still show user input as-is if desired; internally we compare normalized values.
- Future: if we add more normalization (e.g. collapse internal newlines), it stays in one place.

---

## ADR-017: Preserve user prompt edits when generation completes

**Date**: 2026-02-24

**Decision**: When an image generation run completes in the Gradio UI, do not overwrite the prompt textbox with the value that was in effect at the start of the run. Preserve whatever text the user currently has in the box (including any edits they made while generation was in progress).

**Context**: Previously, completion handlers could reset the prompt to the "run" prompt, wiping user edits. Users sometimes tweak the prompt or fix a typo during generation; that edit should not be lost.

**Options Considered**:
1. **Never overwrite prompt on completion**: Chosen. Completion updates image, status, and state; prompt value is left as-is.
2. **Overwrite with "run" prompt**: Predictable but discards user edits.
3. **Ask user or merge**: Adds UI complexity; leave-as-is is simplest and least surprising.

**Rationale**:
- The prompt textbox is the user's working buffer. Generation completion is an outcome, not a signal to revert that buffer.
- Optimized-for state and image result are updated; the visible prompt remains under user control.

**Consequences**:
- Generate completion handlers no longer set the prompt component value from the run's prompt. Any "optimized for" or internal state that tracks the last-used prompt is updated separately from the displayed textbox content.

---

## ADR-018: Package assets for Gradio (logo, favicon)

**Date**: 2026-02-07

**Decision**: Ship logo and favicon as package data under `genimg/assets/logo/` (e.g. favicon.ico, logo_16.png–logo_512.png). Gradio loads favicon via a temp-file copy created from `importlib.resources` so it works when the package is installed from a zip (e.g. `pip install` wheel). Logo path is resolved the same way for the UI header.

**Context**: We want consistent branding in the Gradio UI. Gradio expects a file path for favicon; some installs (zip) don't expose a real filesystem path for package data.

**Options Considered**:
1. **Package data + temp copy for favicon**: Chosen. Zip-safe; single source of truth in package.
2. **External path or URL**: Would require users to configure or host assets.
3. **No favicon / no logo**: Poor branding and UX.

**Rationale**:
- `importlib.resources.files("genimg").joinpath("assets/logo/...").read_bytes()` works for both directory and zip installs. Writing to a temp file gives Gradio a path it can use.
- Temp favicon path is registered with the same temp lifecycle (ADR-013) so it is removed on exit.

**Consequences**:
- `genimg.ui.gradio_app`: `_get_favicon_path()` creates a temp copy on first use; `get_logo_path(size)` returns path for a given size or None. Both use `genimg.assets.logo` package data.
- Adding or changing logo/favicon requires updating files in `src/genimg/assets/logo/` and ensuring package-data includes them (e.g. in pyproject.toml or MANIFEST).

---

## ADR-019: AI process rules in .cursor/rules

**Date**: 2026-02-16

**Decision**: Add Cursor rule files under `.cursor/rules/` that define a repeatable AI-assisted workflow: specification (ai_process_01), implementation plan from spec (ai_process_02), execution of plan (ai_process_03), and release notes from implementation (ai_process_04). Rules are requestable by description so the agent loads them when the user wants to create a spec, plan, implement, or create release notes.

**Context**: We want systematic development (spec → plan → implement → release) without relying on ad-hoc prompts. Cursor rules can encode the process and required context (e.g. "load specification before release notes").

**Options Considered**:
1. **Dedicated .cursor/rules with process steps**: Chosen. Clear separation of steps; agent_requestable so they are loaded when relevant.
2. **Single monolithic rule**: Harder to maintain and to invoke per phase.
3. **External playbook only**: Would not be in-repo or automatically available to the agent.

**Rationale**:
- Each phase has different inputs and outputs; separate rules keep instructions focused and reduce confusion.
- Release notes (ai_process_04) explicitly require verifying implementation against spec, keeping release notes accurate.
- Process is documented in-repo so contributors and future agents can follow it.

**Consequences**:
- `.cursor/rules/ai_process_01_create_specification.mdc` through `ai_process_04_create_release.mdc` exist and are referenced in workspace rules. When the user asks to create a spec, plan, implement a plan, or create release notes, the agent should request and follow the corresponding rule.
- No runtime impact; this is tooling and process for development and release.

---

## Future Decisions to Document

- Batch generation approach
- Progress reporting strategy
