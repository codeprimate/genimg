# CLI Implementation Plan

This document plans the implementation of the `genimg` command-line interface. It aligns with AGENT.md, DECISIONS.md (ADR-002 Click), and docs/SPEC.md.

---

## 1. Current State

- **Entry point**: `genimg` console script and `python -m genimg` both call `genimg.cli.main()` → `cli()`.
- **Framework**: Click (ADR-002). Group `cli` with `--version`; one stub command `generate` with options but no real logic.
- **Constraints** (from AGENT.md):
  - Use **only** the public API: `from genimg import ...` (no `genimg.core.*` / `genimg.utils.*` except for type hints if needed).
  - Config: `Config.from_env()` and optionally `config.validate()` before operations; pass `config=` into library calls.
  - Errors: Map library exceptions to exit codes and user-facing messages.
  - Cancellation: Pass `cancel_check` (e.g. `lambda: cancel_event.is_set()`) to `optimize_prompt` and `generate_image`; set an event on Ctrl+C.

---

## 2. Scope for This Implementation

### In scope

- **Single primary command**: `genimg generate` (or `genimg generate ...`) implementing the full flow: validate → optional optimize → process reference → generate → save/display.
- **Behavior**: One-shot generation from prompt (and optional reference path); optional optimization; config from env; cancellation via Ctrl+C; clear error messages and exit codes.
- **Output**: Save to file (path from `--out` or default) and/or print path; optional brief progress/status messages.

### Out of scope (for now)

- Subcommands like `genimg config`, `genimg cache clear`, `genimg optimize` (optimize-only). Can be added later.
- Interactive prompts for API key or model (env/config only for this phase).
- Batch or multiple outputs per run.

---

## 3. Commands and Options

### 3.1 Command: `generate`

- **Purpose**: Generate one image from a text prompt, with optional prompt optimization and optional reference image.
- **Options** (reflect existing stub and library API):

| Option | Short | Type | Default | Description |
|--------|--------|------|---------|-------------|
| `--prompt` | `-p` | string | required | Text description of the image. |
| `--model` | `-m` | string | from config | OpenRouter image model ID. |
| `--reference` | `-r` | path (exists) | none | Path to reference image file. |
| `--no-optimize` | — | flag | False | Skip prompt optimization (use prompt as-is). |
| `--out` | `-o` | path | see below | Output file path. |
| `--optimization-model` | — | string | from config | Ollama model for optimization (used only if optimization enabled). |
| `--quiet` / `-q` | — | flag | False | Minimize progress messages; only print result path or errors. |

- **Output path rules**:
  - If `--out` / `-o` is set: use it (overwrite if exists; no confirmation in CLI).
  - If not set: default path in current directory, e.g. `genimg_<YYYYMMDD>_<HHMMSS>.<ext>` (extension from API response, typically `jpeg` or `png`).
- **Flow**:
  1. Load config: `Config.from_env()`; call `config.validate()` (fail fast with clear message and exit code if invalid).
  2. Validate prompt (non-empty); library’s `generate_image` also validates, but we can fail early with `validate_prompt` if we want consistent messaging.
  3. If reference path given: call `process_reference_image(path)` → get base64 and hash; on failure map `ImageProcessingError` / `ValidationError` to message and exit code.
  4. If optimization not disabled: call `optimize_prompt(prompt, model=optimization_model, reference_hash=ref_hash, config=config, cancel_check=...)`; use result as the prompt for generation.
  5. Call `generate_image(prompt, model=model, reference_image_b64=ref_b64, config=config, cancel_check=...)`.
  6. Save the image to output path (e.g. `result.image.save(path)` or `path.write_bytes(result.image_data)`); use `GenerationResult.format` for extension if not implied by `--out`.
  7. Print output path (and optionally generation time); on `--quiet`, only print path or error.

### 3.2 Cancellation (Ctrl+C)

- Use a `threading.Event` (e.g. `cancel_event`). On SIGINT (Ctrl+C), set the event.
- Pass `cancel_check=lambda: cancel_event.is_set()` to both `optimize_prompt` and `generate_image`.
- On `CancellationError`: print a short “Cancelled.” message and exit with a dedicated exit code (e.g. 130 to mirror SIGINT, or a project-specific code like 3).
- **Decision**: Use exit code **130** for cancellation (common for SIGINT) so scripts can distinguish it.

### 3.3 Error Handling and Exit Codes

Map exceptions to exit codes and messages:

| Exception | Exit code | Message / behavior |
|-----------|-----------|----------------------|
| `ValidationError` | 2 | Print message (and field if helpful). |
| `ConfigurationError` | 2 | Print message (e.g. missing API key). |
| `APIError`, `NetworkError`, `RequestTimeoutError` | 1 | Print user-friendly message. |
| `ImageProcessingError` | 2 | Print message (e.g. invalid reference image). |
| `CancellationError` | 130 | Print “Cancelled.” (or similar). |
| Other `GenimgError` | 1 | Print message. |
| Unhandled exception | 1 | Print traceback or minimal message (optional: only in debug mode). |

Implementation: a small helper that catches these and calls `sys.exit(code)` after printing, so the rest of the CLI stays free of try/except for known errors.

---

## 4. Implementation Phases

### Phase 1: Core flow and error handling

- Implement `generate` command body:
  - Config load and validate.
  - Parse options; validate prompt (non-empty).
  - If `--reference`: call `process_reference_image`; handle errors.
  - If not `--no-optimize`: call `optimize_prompt(..., config=config)` (no cancel_check first to keep Phase 1 simple).
  - Call `generate_image(..., config=config)`.
  - Determine output path (default or `--out`); write image bytes; print path.
- Add central exception handler: map library exceptions to exit codes and messages; use for the whole `generate` flow.
- **No cancellation in Phase 1** (optional follow-up).

### Phase 2: Cancellation and polish

- Add `threading.Event` and signal handler (or Click’s context) to set event on Ctrl+C.
- Pass `cancel_check` into `optimize_prompt` and `generate_image`.
- Handle `CancellationError` → exit 130 and “Cancelled.” message.
- Default output filename: `genimg_<timestamp>.<ext>` (e.g. from `GenerationResult.format`).
- Add `--quiet` to reduce output.

### Phase 3 (optional)

- `--optimization-model` option.
- Improve default path (e.g. create directory, avoid overwrite by default with a suffix).
- Consider `genimg config check` or `genimg --validate-config` to only validate config and exit 0/2.

---

## 5. File and Module Layout

- **Single module for now**: Keep all CLI in `src/genimg/cli/__init__.py` (one group, one command, one helper for errors). If it grows (e.g. multiple commands), split later into `cli/commands.py` and `cli/errors.py` or similar.
- **Entry point**: Unchanged; `genimg.__main__` calls `genimg.cli.main()`.

---

## 6. Testing Strategy

- **Unit tests** (in `tests/unit/test_cli.py` or under `tests/unit/cli/`):
  - Mock all library calls (`get_config`, `validate_prompt`, `optimize_prompt`, `process_reference_image`, `generate_image`).
  - Test: required `--prompt`; `--no-optimize` skips optimization; `--reference` passes processed image to `generate_image`; `--out` is used for writing; default path is used when `--out` omitted.
  - Test exit codes: invoke CLI with invalid prompt, missing config, and mocked API/validation errors; assert exit code and that appropriate message is printed.
  - Test cancellation: mock `cancel_check` so it returns True after first call; assert `CancellationError` is handled and exit 130 (or chosen code).
- **Integration tests** (optional): Run `genimg generate -p "test" --no-optimize -o /tmp/out.png` with real config and API (or skip in CI if no key).

---

## 7. Open Decisions

1. **Default output path**: Use current directory with `genimg_<timestamp>.<ext>`, or a fixed subdirectory (e.g. `./genimg_output/`)? **Suggestion**: current directory for simplicity; document in help and EXAMPLES.md.
2. **Overwrite**: If `--out` exists, overwrite without prompting. **Suggestion**: overwrite (CLI convention); document.
3. **Exit code for cancellation**: 130 (SIGINT) vs project-specific (e.g. 3). **Suggestion**: 130 for compatibility with shell scripts.
4. **Progress messages**: Short lines like “Optimizing prompt…”, “Generating image…”, “Saved to …” vs only final path. **Suggestion**: print progress unless `--quiet`; with `--quiet` only path or error.

---

## 8. Summary

- Implement **one command**, `generate`, in the existing Click group, using only the public API, `Config.from_env()`, and exception → exit code mapping.
- **Phases**: (1) core flow + error handling, (2) cancellation + default path + `--quiet`, (3) optional extras.
- **Tests**: Unit tests with mocks for library and config; optional integration test.
- **Decisions to confirm**: default path location, overwrite behavior, cancellation exit code (130 recommended), and verbosity vs `--quiet`.

Once these are agreed, implementation can proceed phase by phase and an ADR can be added to DECISIONS.md for the CLI design (exit codes, cancellation, and default behavior).
