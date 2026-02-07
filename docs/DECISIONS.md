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
- **Python 3.8**: Use `Tuple[str, str]` (typing) not `tuple[str, str]` for return types.

---

## Future Decisions to Document

- Batch generation approach
- Progress reporting strategy
- Logging configuration
