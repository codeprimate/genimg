# Development Guide

This guide covers practical development tasks for working on genimg.

## Setup

### Initial Setup

```bash
# Clone repository
git clone <repository-url>
cd genimg

# Create virtual environment
python -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Install package in development mode
pip install -e .

# Install development dependencies
pip install -r requirements-dev.txt
```

### Environment Configuration

Create a `.env` file:

```bash
cp .env.example .env
# Edit .env and add your OpenRouter API key
```

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

1. UI components defined in `create_interface()`
2. Event handlers connected with `.click()`, `.change()`, etc.
3. Use `gr.update()` to modify component state

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

### Version Bump

1. Update version in `src/genimg/__init__.py`
2. Update version in `pyproject.toml`
3. Update CHANGELOG.md

### Build Package

```bash
# Install build tools
pip install build

# Build distribution
python -m build

# Verify contents
tar -tzf dist/genimg-*.tar.gz
```

### Test Installation

```bash
# Create fresh venv
python -m venv test-venv
source test-venv/bin/activate

# Install from wheel
pip install dist/genimg-*.whl

# Test commands
genimg --help
genimg-ui --help

# Deactivate and remove
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
