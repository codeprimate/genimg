# Code Review: Foundation Before CLI

**Date:** February 7, 2026  
**Scope:** Core library and tests vs. SPEC.md, LIBRARY_SPEC.md, DECISIONS.md  
**Goal:** Sanity-check the foundation before implementing the CLI.

---

## Executive Summary

The codebase is **in good shape** for CLI implementation. The library matches the functional spec and library spec: configuration, prompt validation/optimization, image generation, reference image processing, caching, and error types are implemented and tested. A few minor fixes were applied (mypy, type stubs); one **blocker** for install/runtime is the missing entry-point modules. Everything else is either solid or documented as a known gap.

**Verdict:** Foundation is solid. Stub entry points (`__main__.py`, minimal Click CLI, `genimg-ui` stub) were added so the `genimg` and `genimg-ui` commands work; proceed with full CLI implementation.

---

## 1. Spec Alignment

### 1.1 LIBRARY_SPEC.md (Library Operations)

| Requirement | Status | Notes |
|-------------|--------|--------|
| Config: API key, base URL, models, timeouts, max pixels | ✅ | `Config` + `from_env()`; optional `optimization_enabled` |
| Config validation before use | ✅ | `Config.validate()`; `generate_image` checks API key |
| Config per-call or shared | ✅ | `config=` optional; `get_config()` / `set_config()` |
| No API keys in logs/errors | ✅ | `repr=False` on api_key; errors use generic messages |
| Validate prompt (non-empty, acceptable) | ✅ | `validate_prompt()`; also len ≥ 3 |
| Optimize prompt with configurable backend | ✅ | `optimize_prompt()` / `optimize_prompt_with_ollama()` |
| Cache keyed by prompt, model, reference | ✅ | `PromptCache`; `get_cache()`, `clear_cache()`, `get_cached_prompt()` |
| Reference: path or bytes, format, resize 2MP, RGB, base64 + hash | ✅ | `process_reference_image()` |
| Generation: prompt, optional reference, model, return PIL image + metadata | ✅ | `generate_image()` → `GenerationResult` (result.image is PIL; result.image_data for compat) |
| Distinct errors (validation, config, network, API, timeout, image) | ✅ | `utils.exceptions` hierarchy |
| Cancellation | ✅ Implemented | Optional `cancel_check` on optimize_prompt and generate_image; raises CancellationError |

### 1.2 SPEC.md (Product) and Data Requirements

- **Prompt:** Non-empty validated; original preserved by caller. ✅  
- **Reference image:** Formats PNG, JPEG, WebP, HEIC, HEIF; 2MP limit; hash for cache. ✅  
- **Generated image:** `GenerationResult` has `image` (PIL Image, primary), `image_data` and `format` (for backward compatibility), `generation_time`, `model_used`, `prompt_used`, `had_reference`. ✅  
- **Optimized prompt cache:** In-memory, session-scoped; key = hash(prompt, model, reference_hash). ✅  

### 1.3 Integration Contracts (LIBRARY_SPEC §7)

- **OpenRouter:** Bearer token, multimodal message (text + optional image_url), parse JSON base64 or binary body; 401/404/429/5xx and timeout/network mapped to custom errors. ✅  
- **Ollama:** Subprocess `ollama run <model>`, stdin prompt, stdout optimized text; timeout and non-zero exit mapped to `RequestTimeoutError` / `APIError`. ✅  

---

## 2. Architecture and Module Boundaries

- **core/config.py:** Single source for env-loaded config and validation; no secrets in repr.  
- **core/prompt.py:** Validation, Ollama call, cache use; template from `prompts_loader`.  
- **core/image_gen.py:** OpenRouter request/response only; no UI/CLI.  
- **core/reference.py:** Load, validate, resize, RGB, encode; file or bytes.  
- **utils/cache.py:** In-memory `PromptCache`; global `get_cache()` / `clear_cache()`.  
- **utils/exceptions.py:** `GenimgError` base; specific types for CLI/UI to map to messages.  

Dependency flow is one-way: CLI/UI → core + utils; core does not import CLI or UI. Good for testing and for adding the CLI layer.

---

## 3. Public API (genimg/__init__.py)

The package exposes exactly what the library spec and CLI will need:

- **Config:** `Config`, `get_config`, `set_config`  
- **Prompt:** `validate_prompt`, `optimize_prompt`  
- **Image gen:** `generate_image`, `GenerationResult`  
- **Reference:** `process_reference_image`  
- **Cache:** `get_cache`, `clear_cache`, `get_cached_prompt`  
- **Errors:** All custom exception classes  

No internal helpers are exported. Clean and stable for CLI consumption.

---

## 4. Tests

- **107 unit tests**, all passing.  
- **Coverage:** ~95% (target 80% met).  
- **Patterns:** Mocked `requests.post` and `subprocess`; no live OpenRouter/Ollama in unit tests.  
- **Areas covered:** Validation, config/env, cache get/set/clear, image_gen success and error paths, reference load/resize/encode, prompt optimization and cache, exceptions.  

**Gap:** No integration tests (e.g., real Ollama or OpenRouter). Acceptable for “foundation”; add later if desired.

---

## 5. Issues Found and Fixes Applied

| Issue | Fix |
|-------|-----|
| **mypy:** `NetworkError.original_error` default `None` vs `Exception` | Typed as `Optional[Exception]` and added `Optional` import in `exceptions.py`. |
| **mypy:** `content_parts` dict type (text vs image_url shape) | Annotated as `List[Dict[str, Any]]` in `image_gen.py`. |
| **mypy:** Missing stubs for `yaml` | Added `types-PyYAML` to dev deps; mypy passes. |
| **mypy:** `python_version = "3.8"` not supported by mypy | Set to `"3.9"` in `pyproject.toml` (project still `requires-python = ">=3.8"`). |

---

## 6. Known Gaps and Non-Blockers

1. **Entry points**  
   - **Resolved:** `__main__.py` and `genimg.cli` (minimal Click group + `generate` stub) were added so the `genimg` command works. `genimg.ui.gradio_app:launch` stub was added so `genimg-ui` exits with a “not yet implemented” message instead of failing at import.

2. **Cancellation**  
   - Long-running optimization and generation do not support cancellation.  
   - LIBRARY_SPEC allows “when supported.”  
   - **Addressed:** Implemented via optional cancel_check on optimize_prompt and generate_image; DECISIONS ADR-010 updated.

3. **CHANGELOG**  
   - States “Test suite not yet implemented” but 107 tests exist and pass.  
   - **Addressed:** Updated to reflect current state (entry points, CLI stub, test suite, known issues).

4. **reference.py and GIF**  
   - **Addressed:** Removed GIF branch from `_infer_format_from_magic`; only spec-supported formats (PNG, JPEG, WebP, HEIC) are inferred.

5. **Ruff config**  
   - **Addressed:** Moved `select`, `ignore` to `[tool.ruff.lint]` and `per-file-ignores` to `[tool.ruff.lint.per-file-ignores]`.

---

## 7. Recommendations Before Implementing the CLI

1. **CLI implementation under `genimg.cli`**  
   - Stub in place: `genimg` and `genimg generate --help` work.  
   - Implement full behavior: `genimg generate --prompt "..." [--model ...] [--reference ...] [--no-optimize] [--out ...]` (and optionally `genimg optimize`).  
   - Use `Config.from_env()` and optional `config.validate()`; pass `config=` into library calls.  
   - Map library exceptions to exit codes and user-facing messages.

2. **Update CHANGELOG**  
   - **Done:** CHANGELOG updated with current status and known issues.

3. **Keep library interface stable**  
   - **Documented:** AGENT.md section "Implementing the CLI (and UI)" instructs using only the public API, config/error handling, and notes cancellation behavior.

---

## 8. Conclusion

The core library is **spec-compliant**, well-tested, and typed. Entry points are in place; the foundation is solid for implementing the full CLI per SPEC.md and DECISIONS.md.
