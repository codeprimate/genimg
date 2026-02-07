# AGENT.md - AI Agent Development Guide

This document provides essential context for AI agents working on the genimg project. For detailed procedures, see the referenced documentation.

## Project Overview

**genimg** is an AI image generation tool combining OpenRouter's image generation with local Ollama-based prompt optimization. Users interact via CLI, web UI, or Python library.

### Architecture

```
User Input (prompt + optional reference image)
    ↓
Prompt Optimization (optional, via Ollama subprocess)
    ↓
Image Generation (OpenRouter API)
    ↓
Image Output (saved file or displayed in UI)
```

### Key Design Principles

1. **Public API Boundary**: CLI and UI only import from `genimg` root (never `genimg.core.*` or `genimg.utils.*`)
2. **Type Safety**: All functions have type hints; mypy strict mode enforced
3. **Separation of Concerns**: Core logic, UI, CLI, and utils are independent
4. **Error Categories**: Custom exception hierarchy for clear error handling
5. **Session Caching**: In-memory cache for optimized prompts (no persistence)

## Module Structure

```
src/genimg/
├── __init__.py          # Public API (what CLI/UI import)
├── __main__.py          # Entry point for `python -m genimg`
├── core/                # Business logic (INTERNAL - do not import in CLI/UI)
│   ├── config.py        # Configuration management
│   ├── image_gen.py     # OpenRouter API integration
│   ├── prompt.py        # Ollama prompt optimization
│   ├── prompts_loader.py # YAML prompt template loader
│   └── reference.py     # Reference image processing
├── cli/                 # Click CLI (imports from genimg root only)
├── ui/                  # Gradio web UI (imports from genimg root only)
├── utils/               # Utilities (INTERNAL)
│   ├── cache.py         # In-memory prompt cache
│   └── exceptions.py    # Exception hierarchy
├── prompts.yaml         # Bundled prompt templates
└── ui_models.yaml       # UI model dropdown lists
```

### Module Responsibilities

- **core/config.py**: Load/validate API keys, manage model selection, global config instance
- **core/image_gen.py**: Call OpenRouter API, handle multimodal requests, parse responses
- **core/prompt.py**: Validate prompts, call Ollama for optimization, cache results
- **core/reference.py**: Load/resize/encode reference images to base64
- **core/prompts_loader.py**: Load prompt templates from bundled YAML files
- **utils/cache.py**: In-memory hash-based cache for optimized prompts
- **utils/exceptions.py**: Custom exception hierarchy (see below)

### Exception Hierarchy

```
GenimgError (base)
├── ValidationError        # Invalid input (exit code 2)
├── ConfigurationError     # Invalid config (exit code 2)
├── ImageProcessingError   # Image operation failed (exit code 2)
├── CancellationError      # User cancelled (exit code 130)
├── APIError              # OpenRouter API error (exit code 1)
├── NetworkError          # Network/connection error (exit code 1)
└── RequestTimeoutError   # Request timeout (exit code 1)
```

## Python Requirements

- **Version**: Python 3.10+ (required for Gradio 6.x)
- **Style**: black (line-length: 100), ruff, mypy strict
- **Type Hints**: Required on all functions
- **Generics**: Use built-in (`list[str]`, `dict[str, Any]`) - Python 3.10+ syntax

## Virtual Environment (Critical)

**Always use the project venv** (`.venv/`) for all Python commands. Never use system Python or another environment.

### Run commands explicitly with venv executables:

```bash
.venv/bin/pip install -e .
.venv/bin/pytest tests/
.venv/bin/ruff check src/ tests/
.venv/bin/mypy src/
```

### Or activate venv first (if user has done so):

```bash
source .venv/bin/activate  # then: make test, make lint, etc.
```

See `.cursor/rules/venv.mdc` for the full rule.

## Development Workflow

### Before Starting

1. **Read relevant docs first**:
   - `DECISIONS.md` - Understand architectural decisions (ADRs)
   - `SPEC.md` - Functional requirements
   - `DEVELOPMENT.md` - Detailed procedures and common tasks

### Making Changes

1. Implement with tests (maintain >80% coverage)
2. Add type hints to all new functions
3. Use appropriate exception types
4. Run quality checks: `make check-all` (format, lint, typecheck, test)

### Before Committing

```bash
make check-all  # Runs: ruff format, ruff check, mypy, pytest
```

### Documentation Updates

- **DEVELOPMENT.md** - Add detailed procedures for new development tasks
- **EXAMPLES.md** - Add code examples for new features
- **DECISIONS.md** - Document architectural decisions (ADR format)
- **CHANGELOG.md** - Track user-facing changes
- **README.md** - Update if user-facing features change

## Testing

- **Unit tests**: `tests/unit/` - Mock all external dependencies
- **Integration tests**: `tests/integration/` - Real API (manual, opt-in only)
- **Coverage target**: >80% overall, >95% for config/cache
- **Markers**: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`

### Running Tests

```bash
make test              # Unit tests only (default)
make test-integration  # Opt-in: requires GENIMG_RUN_INTEGRATION_TESTS=1
make coverage          # Generate HTML coverage report
```

**Integration tests** call real OpenRouter API (slow, costs money). Excluded by default via `pyproject.toml` (`-m "not integration"`).

## CLI and UI Implementation

### Critical Rule: Public API Only

CLI and UI **must only** import from `genimg` root:

```python
from genimg import (
    Config, generate_image, optimize_prompt, validate_prompt,
    process_reference_image, get_config, clear_cache,
    ValidationError, APIError, CancellationError, ...
)
```

**Never** import from `genimg.core.*` or `genimg.utils.*` in CLI/UI code.

### CLI Exit Codes

- `0` - Success
- `1` - API/Network errors (`APIError`, `NetworkError`, `RequestTimeoutError`)
- `2` - Validation/Config errors (`ValidationError`, `ConfigurationError`, `ImageProcessingError`)
- `130` - Cancellation (`CancellationError` - standard SIGINT code)

### Cancellation Pattern

```python
import threading
cancel_event = threading.Event()

# In SIGINT handler: cancel_event.set()

result = generate_image(
    prompt="...",
    cancel_check=lambda: cancel_event.is_set()
)
```

Library polls `cancel_check()` every 250ms; raises `CancellationError` when True. For Ollama, subprocess is terminated.

## Configuration

### Environment Variables

**Required:**
- `OPENROUTER_API_KEY` - OpenRouter API key (format: `sk-or-v1-...`)
  - Can also be provided via CLI: `genimg generate --api-key sk-or-v1-...` or `genimg ui --api-key sk-or-v1-...`

**Optional:**
- `GENIMG_DEFAULT_MODEL` - Default image model (default: `bytedance-seed/seedream-4.5`)
- `GENIMG_OPTIMIZATION_MODEL` - Ollama model (default: `svjack/gpt-oss-20b-heretic`)
- `GENIMG_UI_PORT`, `GENIMG_UI_HOST`, `GENIMG_UI_SHARE` - UI launch options
- `GENIMG_VERBOSITY` - Logging verbosity: `0` (default: activity/performance), `1` (also prompts), `2` (verbose: API/cache). CLI `-v`/`-vv` override.
- `GENIMG_RUN_INTEGRATION_TESTS` - Enable integration tests (set to `1`)

See `.env.example` for full reference.

## Common Patterns

See `EXAMPLES.md` for detailed code examples. Key patterns:

- **Config**: Use `Config.from_env()` and call `config.validate()` before operations
- **Errors**: Use appropriate exception types from `utils.exceptions`
- **Cache**: Access via `get_cache()`, clear with `clear_cache()`
- **Images**: Process reference images with `process_reference_image()`
- **Prompts**: Load templates via `prompts_loader.get_optimization_template()`

## Key Implementation Details

### OpenRouter API
- May return JSON (`choices[0].message.images[]`) or direct image (`content-type: image/*`)
- Always check content-type header first

### Ollama Integration
- Runs as subprocess via `Popen`
- Handles timeout with `communicate(timeout=...)`
- Terminated on cancellation

### Image Processing
- Reference images resized to 2MP (maintains aspect ratio)
- Requires `pillow-heif` for HEIC/HEIF support
- RGBA converted to RGB (composite on white background)

### Package Data
- `prompts.yaml` and `ui_models.yaml` bundled with package
- Accessed via `importlib.resources.files("genimg").joinpath("file.yaml")`
- Declared in `pyproject.toml` under `[tool.setuptools.package-data]`

## Getting Help

- **DEVELOPMENT.md** - Detailed procedures for common development tasks
- **EXAMPLES.md** - Code examples for library, CLI, and error handling
- **DECISIONS.md** - Architecture Decision Records (ADRs) explaining design choices
- **SPEC.md** - Functional requirements and user capabilities
- **README.md** - User-facing documentation and quick start

## Quick Reference

### Make Targets
- `make install-dev` - Install with dev dependencies
- `make check-all` - Run all quality checks (format, lint, typecheck, test)
- `make test`, `make test-unit`, `make test-integration` - Run tests
- `make coverage` - Generate HTML coverage report
- `make clean` - Remove build artifacts

### Console Scripts
- `genimg generate "prompt"` - Generate image
- `genimg ui` - Launch web UI
- `genimg-ui` - Launch web UI (direct entry point)
- `python -m genimg` - Alternative CLI invocation
