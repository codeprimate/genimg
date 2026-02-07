# Development Guide

This guide covers practical development tasks for working on genimg.

## Setup

### Initial Setup

```bash
# Clone repository
git clone https://github.com/codeprimate/genimg.git
cd genimg

# Create virtual environment
python -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Install package in development mode with dev dependencies (recommended)
make install-dev
# Or manually:
# pip install -e .
# pip install -r requirements-dev.txt
```

### Environment Configuration

Create a `.env` file:

```bash
cp .env.example .env
# Edit .env and add your OpenRouter API key
```

#### Environment Variables Reference

**Required:**
- `OPENROUTER_API_KEY` — OpenRouter API key (format: `sk-or-v1-...`). Get from https://openrouter.ai/keys
  - Can also be provided via CLI: `genimg generate --api-key sk-or-v1-...`

**Optional (Image Generation):**
- `GENIMG_DEFAULT_MODEL` — Default image generation model (default: `bytedance-seed/seedream-4.5`)
- `GENIMG_OPTIMIZATION_MODEL` — Default Ollama model for prompt optimization (default: `svjack/gpt-oss-20b-heretic`)

**Optional (Web UI):**
- `GENIMG_UI_PORT` — Gradio server port (default: 7860)
- `GENIMG_UI_HOST` — Server host binding (default: 127.0.0.1; use 0.0.0.0 for LAN access)
- `GENIMG_UI_SHARE` — Create public share link (set to "1" or "true" for gradio.live link)

**Optional (Testing):**
- `GENIMG_RUN_INTEGRATION_TESTS` — Enable integration tests (set to "1" to opt-in; default: disabled)

See `.env.example` for a complete template with all variables.

### Verify Setup

**Use the project venv** so tests and tools see the right dependencies. (AI agents: see AGENT.md "Virtual environment (venv)" and the Cursor rule in `.cursor/rules/venv.mdc`.) Either activate it first:

```bash
source .venv/bin/activate   # Linux/Mac
# or  .venv\Scripts\activate  # Windows
make test
make lint
make typecheck
```

Or run the venv's executables directly (e.g. in CI or without activating):

```bash
.venv/bin/pip install -e .
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests/
.venv/bin/ruff check src/ tests/
.venv/bin/mypy src/
```

```bash
# Run tests
make test

# Check linting
make lint

# Type check
make typecheck
```

### Integration tests (manual, slow, costs money)

Integration tests call the real OpenRouter API. They are **excluded from the default test run** (`make test` / `pytest`). Run them only when you need to verify the live API:

```bash
# Opt-in: set env and run integration tests only
GENIMG_RUN_INTEGRATION_TESTS=1 make test-integration
# or
GENIMG_RUN_INTEGRATION_TESTS=1 .venv/bin/pytest -m integration
```

Requirements:

- `GENIMG_RUN_INTEGRATION_TESTS=1` (opt-in so they never run by accident)
- `OPENROUTER_API_KEY` set in `.env` or environment

## Library API

The library is the single source of truth for all product behavior (see LIBRARY_SPEC.md).

- **Configuration**: Pass `config` per operation (e.g. `generate_image(..., config=my_config)`) or use the shared config via `get_config()` / `set_config()`. When passing config explicitly, the caller may call `config.validate()` before use if the operation depends on credentials.
- **Cache**: The prompt optimization cache is process-scoped. Use `clear_cache()` and `get_cached_prompt()` for cache management; `get_cache()` gives direct access to the cache instance.
- **API keys**: The library does not log or expose API keys in error messages, return values, or config repr.
- **Testability**: Backends (HTTP client, Ollama subprocess) are not yet injectable; a future improvement for unit tests would be dependency injection of the HTTP client and optimizer so tests do not require network or Ollama.

## Common Development Tasks

### Adding a New Image Generation Model

1. Model ID goes in `.env` or passed as parameter
2. No code changes needed (OpenRouter handles routing)
3. Update README.md with model name if it's recommended

### Adding a New Optimization Model

1. Install model in Ollama: `ollama pull <model-name>`
2. Set in environment: `GENIMG_OPTIMIZATION_MODEL=<model-name>`
3. Or pass as parameter to `optimize_prompt()`

### Changing the Prompt Optimization Template

Edit the `optimization.template` section in `src/genimg/prompts.yaml`. The template must include the placeholder `{original_prompt}`. Other prompt templates can be added there and loaded via `genimg.core.prompts_loader.get_prompt(key, subkey)`. Run tests to verify after changes.

### Adding a New CLI Command

1. Edit `src/genimg/cli/commands.py`
2. Add new Click command:

```python
@cli.command()
@click.argument("arg")
@click.option("--option", help="Description")
def newcommand(arg, option):
    """Command description."""
    # Implementation
```

3. Add tests in `tests/unit/test_cli.py`

### Modifying the Gradio UI

Edit `src/genimg/ui/gradio_app.py`:

1. UI layout and components are built in `_build_blocks()`.
2. Event handlers are connected with `.click()`, `.change()`, etc.
3. Use `gr.update()` to modify component state (e.g. button `interactive`).

**Running the UI:** `genimg-ui` or `genimg ui` (with optional `--port`, `--host`, `--share`). Environment: `GENIMG_UI_PORT` (default 7860), `GENIMG_UI_HOST` (default 127.0.0.1), `GENIMG_UI_SHARE` (set to `1` or `true` for a public link).

### Adding a New Error Type

1. Add to `src/genimg/utils/exceptions.py`:

```python
class NewError(GenimgError):
    """Description of when this error occurs."""
    
    def __init__(self, message: str, custom_field: str = "") -> None:
        self.custom_field = custom_field
        super().__init__(message)
```

2. Export in `src/genimg/__init__.py`
3. Add tests in `tests/unit/test_exceptions.py`

## Implementation Patterns

### Using the Public API

CLI and UI code must only import from the `genimg` root package:

```python
# ✅ CORRECT - Import from public API
from genimg import (
    Config, generate_image, optimize_prompt, validate_prompt,
    process_reference_image, get_config, set_config, clear_cache,
    ValidationError, APIError, CancellationError, GenimgError
)

# ❌ WRONG - Do not import from internal modules
from genimg.core.config import Config
from genimg.utils.exceptions import ValidationError
```

### Configuration Pattern

```python
from genimg import Config

# Load from environment
config = Config.from_env()

# Validate before use
config.validate()  # Raises ConfigurationError if invalid

# Override programmatically
config.default_model = "openai/gpt-5-image"
config.optimization_enabled = True

# Or set API key directly (useful in CLI)
config.set_api_key("sk-or-v1-your-key-here")

# Pass to operations
result = generate_image(prompt="...", config=config)
```

### Error Handling with Exit Codes (CLI)

```python
from genimg import ValidationError, APIError, NetworkError, CancellationError
import sys

try:
    # operation
    result = generate_image(...)
except ValidationError as e:
    print(f"Validation error: {e}", file=sys.stderr)
    sys.exit(2)  # EXIT_VALIDATION_OR_CONFIG
except (APIError, NetworkError) as e:
    print(f"API error: {e}", file=sys.stderr)
    sys.exit(1)  # EXIT_API_OR_NETWORK
except CancellationError:
    print("Cancelled.", file=sys.stderr)
    sys.exit(130)  # EXIT_CANCELLED (standard SIGINT code)
```

### Cancellation Support

```python
import threading
from genimg import generate_image, optimize_prompt, CancellationError

cancel_event = threading.Event()

# In your SIGINT handler (or UI cancel button):
def handle_cancel():
    cancel_event.set()

# Pass cancel_check to operations
try:
    result = generate_image(
        prompt="...",
        cancel_check=lambda: cancel_event.is_set()
    )
except CancellationError:
    print("Operation cancelled by user")
```

**How it works:**
- Library polls `cancel_check()` every 250ms
- When it returns True, library raises `CancellationError`
- For Ollama: subprocess is terminated
- For OpenRouter: HTTP request may complete in background (no sync abort)

### Using the Cache

```python
from genimg import get_cache, clear_cache, get_cached_prompt

# Get cache instance
cache = get_cache()

# Check for cached value
cached = cache.get(prompt, model, reference_hash)
if cached:
    return cached

# Set cached value
cache.set(prompt, model, optimized_prompt, reference_hash)

# Clear entire cache
clear_cache()

# Get specific cached prompt
cached_prompt = get_cached_prompt(prompt, model, reference_hash)
```

### Loading Prompt Templates

```python
from genimg.core.prompts_loader import get_optimization_template, get_prompt

# Get optimization template (includes {reference_image_instruction} placeholder)
template = get_optimization_template()

# Get any prompt by key
custom_prompt = get_prompt("optimization", "template")
```

### Processing Reference Images

```python
from genimg import process_reference_image

# Process and encode image
encoded_b64, image_hash = process_reference_image("/path/to/image.jpg")

# Use in generation
result = generate_image(
    prompt="...",
    reference_image_b64=encoded_b64
)

# Use hash for cache key
cached = get_cached_prompt(prompt, model, reference_hash=image_hash)
```

### Accessing Package Data Files

```python
import importlib.resources
import yaml

# Load bundled YAML files (prompts.yaml, ui_models.yaml)
with importlib.resources.files("genimg").joinpath("prompts.yaml").open(encoding="utf-8") as f:
    data = yaml.safe_load(f)
```

## Testing

### Running Tests

```bash
# All tests
make test

# Unit tests only
make test-unit

# Integration tests only
make test-integration

# With coverage
make coverage
open htmlcov/index.html  # View coverage report

# Specific test file
pytest tests/unit/test_config.py

# Specific test function
pytest tests/unit/test_config.py::test_config_from_env

# With verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Writing Tests

#### Unit Test Pattern

```python
import pytest
from genimg.core.module import function
from genimg.utils.exceptions import ErrorType

def test_function_success():
    """Test successful operation."""
    result = function(valid_input)
    assert result == expected

def test_function_validation_error():
    """Test validation error."""
    with pytest.raises(ErrorType) as exc_info:
        function(invalid_input)
    assert "expected message" in str(exc_info.value)

@pytest.mark.slow
def test_slow_operation():
    """Mark slow tests."""
    # Test that takes >1s
```

#### Using Fixtures

```python
def test_with_config(test_config):
    """Use fixture from conftest.py."""
    assert test_config.openrouter_api_key

def test_with_sample_image(sample_png_image):
    """Use sample image fixture."""
    assert sample_png_image.exists()
```

#### Mocking External Calls

```python
from unittest.mock import patch, Mock

def test_api_call(mock_openrouter_success):
    """Mock API responses."""
    result = generate_image("test prompt")
    assert result.image_data

@patch('subprocess.Popen')
def test_ollama_call(mock_popen):
    """Mock subprocess calls."""
    mock_popen.return_value.communicate.return_value = ("output", "")
    result = optimize_prompt("test")
    assert result
```

## Code Quality

### Formatting

```bash
# Format all code
make format

# Check formatting without changes
black --check src/ tests/
```

### Linting

```bash
# Lint and auto-fix
make lint

# Lint without fixes
ruff check src/ tests/

# Lint specific file
ruff check src/genimg/core/config.py
```

### Type Checking

```bash
# Type check all code
make typecheck

# Type check specific file
mypy src/genimg/core/config.py

# Ignore specific error
# (Add inline comment)
value = func()  # type: ignore[error-code]
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Test API Connections

```bash
# Test OpenRouter connection
python scripts/test_api.py

# Test Ollama installation
python scripts/test_ollama.py
```

### Inspect Cache Contents

```python
from genimg.utils.cache import get_cache

cache = get_cache()
print(f"Cache size: {cache.size()}")
```

Or use the inspection script:

```bash
python scripts/inspect_cache.py
```

## Gotchas & Implementation Details

### OpenRouter API Integration

**Response Format Variations:**
- May return JSON with `choices[0].message.images[]` (array of base64 strings)
- Or may return direct image bytes with `content-type: image/*`
- **Always check content-type header first** to determine response format

**Best Practices:**
- Handle both response formats
- Check for error responses before parsing
- Include model name in requests for proper routing

### Ollama Subprocess Management

**Implementation:**
- Uses `subprocess.Popen` for subprocess control
- Calls `communicate(timeout=...)` for timeout support
- Always handle `TimeoutExpired` exception
- Check `returncode` for subprocess errors

**On Cancellation:**
- Call `process.terminate()` to stop subprocess
- Subprocess is actually killed (not just abandoned)
- Join worker thread with timeout to ensure cleanup

**Limitations:**
- No streaming support (reads full response)
- Blocking operation (runs in worker thread for cancellation)

### Image Processing

**Reference Image Resizing:**
- All reference images resized to 2MP (maintains aspect ratio)
- Use `Image.Resampling.LANCZOS` for quality
- Calculate scale based on total pixels, not dimensions
- Example: 4000x3000 (12MP) → resized to ~1633x1225 (2MP)

**Color Mode Conversion:**
- RGBA converted to RGB (composite on white background)
- Use alpha channel for proper transparency handling
- All images converted to RGB before encoding

**HEIC/HEIF Support:**
- Requires optional `pillow-heif` library
- Register opener: `from pillow_heif import register_heif_opener; register_heif_opener()`
- Gracefully degrades if library not installed (error message to user)

### Configuration Management

**API Key Security:**
- API keys validated format (`sk-or-v1-...` for OpenRouter)
- Keys never logged or exposed in error messages
- Config `__repr__` masks API keys
- Environment variables loaded early via `python-dotenv`

**Config Validation:**
- Call `config.validate()` before operations that need API keys
- Raises `ConfigurationError` with helpful message if invalid
- Optional validation (some operations don't need all config)

### Caching

**Cache Key Strategy:**
- Hash-based: `prompt + model + reference_hash`
- Reference hash is SHA256 of image bytes
- No cache key collisions (hash includes all inputs)

**Cache Lifetime:**
- Session-scoped (process lifetime)
- No disk persistence (intentional - optimization is fast enough)
- Cleared on process exit or explicit `clear_cache()`

**Memory Considerations:**
- Cache grows with unique prompts
- Bounded by session length (typically short)
- Each cached entry stores optimized prompt string (~500-2000 chars)

### Package Data Files

**Bundled YAML Files:**
- `prompts.yaml` - Prompt templates
- `ui_models.yaml` - Model dropdown lists for UI
- Declared in `pyproject.toml`: `[tool.setuptools.package-data]`
- Access via `importlib.resources.files("genimg").joinpath("file.yaml")`
- Cached after first load (module-level cache in `prompts_loader.py`)

### Testing

**Integration Test Safeguard:**
- Must set `GENIMG_RUN_INTEGRATION_TESTS=1` to enable
- Prevents accidental API calls and costs during dev
- Default `pytest` excludes via `-m "not integration"` in `pyproject.toml`

**Mocking External Dependencies:**
- Mock `subprocess.Popen` for Ollama tests
- Mock `requests.post` for OpenRouter tests
- Use `pytest-mock` for simple mocking
- Use `responses` library for detailed HTTP mocking

### CLI Exit Codes

Standard exit codes for consistent error handling:

```python
EXIT_SUCCESS = 0                  # Success
EXIT_API_OR_NETWORK = 1          # APIError, NetworkError, RequestTimeoutError
EXIT_VALIDATION_OR_CONFIG = 2    # ValidationError, ConfigurationError, ImageProcessingError
EXIT_CANCELLED = 130             # CancellationError (standard SIGINT code)
```

### Cancellation Polling

**Implementation Details:**
- Poll interval: 250ms (adequate for <100ms response in practice)
- Worker threads are daemon threads (don't block process exit)
- `cancel_check` should return quickly and not raise exceptions
- Library catches and ignores exceptions from `cancel_check` (buggy callback won't abort operation)

**Platform Differences:**
- OpenRouter: HTTP request may complete in background after cancel (requests has no sync abort from another thread)
- Ollama: Subprocess actually terminated via `process.terminate()`
- Thread accumulation: Repeated cancel-and-retry leaves worker threads until requests finish (acceptable for CLI; consider thread pool for long-lived servers)

### Trace Image Processing

Add debug prints in `core/reference.py`:

```python
print(f"Original size: {image.size}")
print(f"Resized to: {new_image.size}")
print(f"Format: {image.format}")
```

### Common Error Patterns

**"Ollama is not available"**:
- Check: `which ollama`
- Check: `ollama list`
- Install if missing

**"OpenRouter API key is required"**:
- Check: `echo $OPENROUTER_API_KEY`
- Check `.env` file exists and is loaded
- Verify key starts with "sk-"

**Image format errors**:
- Check supported formats in `core/reference.py`
- For HEIC: Install `pillow-heif`
- Use PIL to verify: `from PIL import Image; Image.open(path)`

**Type errors**:
- Run `mypy` to see all type issues
- Check type hint matches actual usage
- Add `# type: ignore` only as last resort

## Performance

### Profile Generation Time

```python
import time

start = time.time()
result = generate_image("prompt")
print(f"Generation took: {result.generation_time:.2f}s")
print(f"Total time: {time.time() - start:.2f}s")
```

### Profile Optimization Time

```python
import time

start = time.time()
result = optimize_prompt("prompt")
elapsed = time.time() - start
print(f"Optimization took: {elapsed:.2f}s")
```

### Memory Usage

```bash
# Use memory_profiler
pip install memory_profiler

# Decorate function
@profile
def function():
    pass

# Run with profiler
python -m memory_profiler script.py
```

### Bottlenecks

Typical bottlenecks:
1. **Ollama calls**: 5-30s depending on model and hardware
2. **OpenRouter API**: 3-60s depending on model and complexity
3. **Image processing**: Usually <1s even for large images
4. **Cache lookups**: Negligible (~1ms)

## Release Process

The release workflow builds source and wheel distributions, installs using the built wheel, and publishes by running clean → build → twine check → upload.

### Version Bump

1. Update version in `src/genimg/__init__.py`
2. Update version in `pyproject.toml`
3. Update CHANGELOG.md

### Build and Install (Makefile)

Ensure the project venv is set up and dev dependencies installed (including `build` and `twine` via `.[dev]`):

```bash
# Install dev deps (includes build, twine)
make install-dev

# Build sdist + wheel (cleans first)
make build

# Install the built wheel into current env
make install

# Or for day-to-day development: editable install with dev deps
make install-dev
```

### Validate and Publish to PyPI

```bash
# Check distribution files
make check

# Full publish: clean → build → check → twine upload
make publish
```

You will be prompted for PyPI credentials (username `__token__`, password = your API token).

### Test Installation (manual)

To verify the wheel in a clean environment:

```bash
python -m venv test-venv
source test-venv/bin/activate
pip install dist/genimg-*.whl
genimg --help
genimg-ui --help
deactivate
rm -rf test-venv
```

## Troubleshooting Development Issues

### "ModuleNotFoundError: No module named 'genimg'"

Install in editable mode:
```bash
pip install -e .
```

### "ImportError: cannot import name"

Circular import issue. Check import order in `__init__.py`.

### Tests pass locally but fail in CI

- Check Python version (CI may use different version)
- Check dependencies in requirements-dev.txt
- Look for environment-specific code

### Type checking passes locally but fails in CI

- Different mypy version
- Different Python version
- Missing type stubs

## Best Practices

1. **Write tests first** (or at least alongside implementation)
2. **Run `make check`** before committing
3. **Keep functions small** (<50 lines ideally)
4. **Use type hints** on all new code
5. **Handle errors gracefully** with custom exceptions
6. **Document complex logic** with comments
7. **Update AGENT.md** when discovering gotchas
8. **Update DECISIONS.md** when making architectural choices
