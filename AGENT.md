# AGENT.md - AI Agent Development Guide

This document provides guidance for AI agents working on the genimg project. It contains architectural context, coding patterns, and development practices.

## Project Overview

**genimg** is an AI image generation tool that combines OpenRouter's image generation capabilities with local Ollama-based prompt optimization. Users can generate images via CLI, web UI, or Python library.

### Core Architecture

```
User Input (prompt + optional reference image)
    ↓
Prompt Optimization (optional, via Ollama)
    ↓
Image Generation (OpenRouter API)
    ↓
Image Output (saved file or displayed in UI)
```

### Key Design Principles

1. **Separation of Concerns**: Core logic, UI, CLI, and utils are separate
2. **Type Safety**: All functions have type hints
3. **Error Handling**: Custom exceptions for different error categories
4. **Caching**: In-memory cache for optimized prompts (session-scoped)
5. **Configurability**: Environment variables + programmatic configuration

## Module Responsibilities

### `core/config.py`
- Loads and validates API keys
- Manages model selection
- Provides global config instance
- **Key Classes**: `Config`
- **Key Functions**: `get_config()`, `set_config()`

### `core/prompt.py`
- Validates prompts
- Calls Ollama for optimization
- Uses subprocess to run `ollama run <model>`
- Caches optimized prompts
- **Key Functions**: `optimize_prompt()`, `validate_prompt()`

### `core/image_gen.py`
- Calls OpenRouter API
- Handles multimodal requests (text + optional image)
- Parses responses (JSON with base64 or direct image)
- Tracks generation time
- **Key Functions**: `generate_image()`
- **Key Classes**: `GenerationResult`

### `core/reference.py`
- Loads and validates reference images
- Resizes to 2MP limit
- Converts to RGB
- Encodes to base64
- **Key Functions**: `process_reference_image()`, `get_image_hash()`

### `utils/cache.py`
- In-memory prompt caching
- Hash-based keys (prompt + model + reference_hash)
- Session-scoped (no persistence)
- **Key Classes**: `PromptCache`
- **Key Functions**: `get_cache()`, `clear_cache()`

### `utils/exceptions.py`
- Custom exception hierarchy
- Base: `GenimgError`
- Specific: `ValidationError`, `APIError`, `NetworkError`, `CancellationError`, `ConfigurationError`, `ImageProcessingError`

## Implementing the CLI (and UI)

When adding or changing CLI or UI code:

- **Use only the public API.** Import from `genimg` (the package root), e.g. `from genimg import get_config, generate_image, validate_prompt, optimize_prompt, process_reference_image, clear_cache, ...` and the exception classes. Do **not** import from `genimg.core.*` or `genimg.utils.*` in CLI/UI code, except for type hints if strictly needed.
- **Config:** Use `Config.from_env()` and optionally `config.validate()` before operations; pass `config=` into library calls so behavior is testable and overridable.
- **Errors:** Map library exceptions to exit codes and user-facing messages (e.g. `ValidationError` → 2, `APIError` / `NetworkError` → 1). See `genimg.utils.exceptions` for the full hierarchy.
- **Cancellation:** Pass optional `cancel_check: Callable[[], bool]` (e.g. `lambda: cancel_event.is_set()`) to `optimize_prompt` and `generate_image`; when it returns True the library raises `CancellationError` and (for Ollama) terminates the subprocess. CLI can set an event on Ctrl+C and pass it as cancel_check.

## Python Practices

### Python Version
- Minimum: Python 3.8
- Target: 3.8, 3.9, 3.10, 3.11

### Type Hints
- All functions must have type hints
- Use `Optional[T]` for nullable types
- Use `from typing import` for compatibility with Python 3.8

### Code Style
- **Formatter**: black (line-length: 100)
- **Linter**: ruff (replaces flake8, isort, etc.)
- **Type Checker**: mypy (strict mode)

### Error Handling Pattern
```python
try:
    # Operation
    pass
except SpecificError as e:
    raise CustomException("User-friendly message", ...) from e
```

### Configuration Pattern
```python
config = get_config()  # Global instance
config.validate()      # Always validate before use
```

### API Call Pattern
```python
try:
    response = requests.post(url, json=payload, timeout=timeout)
    if response.status_code != 200:
        raise APIError(...)
except requests.exceptions.Timeout:
    raise NetworkError(...)
```

## Testing Practices

### Test Organization
- `tests/unit/`: Unit tests (mock all external dependencies)
- `tests/integration/`: Integration tests (may use real APIs in CI)
- `tests/fixtures/`: Shared fixtures and sample data

### Coverage Requirements
- Overall: >80%
- Critical modules (config, cache): >95%
- Exceptions module: 100%

### Pytest Markers
- `@pytest.mark.unit`: Unit test
- `@pytest.mark.integration`: Integration test  
- `@pytest.mark.slow`: Slow-running test

### Running Tests
Use the project venv (see "Virtual environment (venv)" above):
```bash
.venv/bin/pytest tests/        # All tests
.venv/bin/pytest tests/unit/  # Unit only
.venv/bin/pytest tests/ -v     # Verbose
make test                      # Same, if venv is already activated
make test-unit
make test-integration
make coverage
```

## Virtual environment (venv) — required

**Always use the project venv for Python commands.** Do not run `python`, `pip`, `pytest`, `ruff`, or `mypy` with the system or another environment. The project uses `.venv/` (see .gitignore).

### When you run commands

1. **Preferred (no shell activation):** Use the venv’s executables explicitly so the right environment is used every time:
   ```bash
   .venv/bin/pip install -e .
   .venv/bin/pip install -r requirements-dev.txt
   .venv/bin/pytest tests/
   .venv/bin/ruff check src/ tests/
   .venv/bin/ruff format src/ tests/
   .venv/bin/mypy src/
   ```
2. **If the user has activated the venv:** `make test`, `make lint`, `make typecheck`, and `make check` will use the activated environment. Only rely on this when you know the venv is active (e.g. the user said they activated it).
3. **In CI or automation:** Always call `.venv/bin/python`, `.venv/bin/pytest`, etc., or run in a step that activates `.venv` first.

### Ensure venv exists

If `.venv` might not exist (e.g. fresh clone), create and install before running tests or tools:
```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pip install -r requirements-dev.txt
```
Then use `.venv/bin/pytest` (and similar) for all subsequent commands.

### Why this matters

- Running `pytest` or `make test` without the project venv can use a different Python and miss project dependencies (e.g. pytest not found, wrong package).
- Explicit `.venv/bin/...` commands are deterministic and work even when the shell is not activated.

## Development Workflow

### Setup
```bash
python -m venv .venv
source .venv/bin/activate   # optional if you will use .venv/bin/... for every command
.venv/bin/pip install -e .
.venv/bin/pip install -r requirements-dev.txt
```

### Before Committing
```bash
make check  # Runs: format, lint, typecheck, test — ensure venv is active or use .venv/bin/... for each tool
```

### Adding a New Feature
1. Update DECISIONS.md if architectural
2. Implement core logic with tests
3. Update UI/CLI if needed
4. Run quality checks
5. Update documentation

## Common Patterns

### Validating User Input
```python
from genimg.utils.exceptions import ValidationError

if not value or not value.strip():
    raise ValidationError("Field cannot be empty", field="field_name")
```

### Using the Cache
```python
from genimg.utils.cache import get_cache

cache = get_cache()
cached_value = cache.get(key, model, ref_hash)
if cached_value:
    return cached_value
# ... compute value ...
cache.set(key, model, value, ref_hash)
```

### Processing Images
```python
from genimg.core.reference import process_reference_image

encoded, hash = process_reference_image("/path/to/image.jpg")
# encoded: base64 string
# hash: SHA256 hash for caching
```

## Gotchas & Lessons Learned

### API Integration

**OpenRouter Response Formats**:
- May return JSON with `choices[0].message.images[]`
- Or may return direct image with `content-type: image/*`
- Always check content-type header first

**Ollama Subprocess**:
- Use `subprocess.Popen` with `communicate()` for timeout support
- Always handle `TimeoutExpired` and kill process
- Check `returncode` for errors

### Image Processing

**HEIC/HEIF Support**:
- Requires `pillow-heif` library
- Register opener: `from pillow_heif import register_heif_opener; register_heif_opener()`
- Fails gracefully if library not installed

**Image Resizing**:
- Use `Image.Resampling.LANCZOS` for quality
- Calculate scale based on total pixels, not dimensions
- Always maintain aspect ratio

**RGB Conversion**:
- Handle RGBA by compositing on white background
- Use alpha channel for proper transparency

### Configuration

**Environment Variables**:
- Load via `python-dotenv`
- Call `load_dotenv()` early (done in config.py)
- Validate API keys (must start with "sk-")

## Module Interdependencies

```
utils/exceptions.py (base - no dependencies)
    ↓
utils/cache.py
    ↓
core/config.py
    ↓
core/reference.py
    ↓
core/prompt.py → uses cache
    ↓
core/image_gen.py → uses reference
    ↓
cli/commands.py, ui/gradio_app.py
```

## Future Improvements

- Async support for concurrent generations
- Persistent cache (disk-based)
- Streaming support for Ollama
- Progress callbacks for long operations
- Batch generation support

## External Dependencies

### Critical
- **requests**: HTTP client for OpenRouter
- **pillow**: Image processing
- **gradio**: Web UI framework
- **click**: CLI framework
- **python-dotenv**: Environment variable loading

### Optional
- **pillow-heif**: HEIC/HEIF format support

### Development
- **pytest**: Testing framework
- **black**: Code formatter
- **ruff**: Linter
- **mypy**: Type checker
- **pytest-cov**: Coverage reporting

## When Making Changes

1. **Read DECISIONS.md** first - understand why things are the way they are
2. **Update tests** - maintain >80% coverage
3. **Run linters** - `make check` before committing
4. **Update EXAMPLES.md** - if adding new features
5. **Update this file** - capture new patterns or gotchas
6. **Update CHANGELOG.md** - track what changed

## Getting Help

- Check EXAMPLES.md for usage patterns
- Check DEVELOPMENT.md for common tasks
- Check DECISIONS.md for architectural context
- Read the SPEC.md for requirements
