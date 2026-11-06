# AGENTS.md

## Purpose

`genimg` is an AI image generation tool: prompt text (+ optional reference image) → optional
prompt optimization via local Ollama HTTP → image via a provider (OpenRouter, Wiro, Ollama,
Draw Things gRPC) → saved file or UI output. Three surfaces: Click CLI (`genimg`), Gradio UI
(`genimg-ui`), and a Python library.

Project docs live in `docs/`: `SPEC.md`, `DECISIONS.md` (ADRs), `DEVELOPMENT.md` (procedures and
common tasks), `EXAMPLES.md`, `CHANGELOG.md`, `releases/`. User-facing docs: `README.md`.
Detailed API surface, exception hierarchy, and exit codes are in `docs/DEVELOPMENT.md`.

Source layout: `src/genimg/` holds `core/` (business logic), `core/providers/` (provider
registry and backends), `core/image_analysis/`, `cli/`, `ui/`, `utils/`, `contrib/`.

## Setup

The venv at `.venv/` is managed by **uv** (see `uv.lock`). It has no `pip`. Use the venv's own
executables for `pytest`, `ruff`, `mypy`, and `genimg`; use uv to install.

```bash
uv pip install --python .venv/bin/python -e .
uv pip install --python .venv/bin/python -r requirements-dev.txt
```

Never call system `python`, `pip`, `pytest`, `ruff`, or `mypy`. The Makefile `install`,
`install-dev`, and `uninstall` targets call a bare `pip` and fail here; install with uv instead.

## Commands

Everything below targets venv executables, so no activation is needed.

```bash
# Test
make test                     # .venv/bin/pytest — all non-slow tests, coverage floor 80%
make test-unit                # .venv/bin/pytest -m unit
.venv/bin/pytest tests/unit/test_config.py -x        # one file
make coverage                 # HTML report in htmlcov/index.html

# Lint, format, types
make lint                     # .venv/bin/ruff check .   (whole project)
make format                   # .venv/bin/ruff format . && ruff check --fix .
make typecheck                # .venv/bin/mypy src/   (src only; not tests or scripts)
make check-all                # format, lint, typecheck, test — run before every commit

# Build and release (ask the user first)
make build                    # sdist + wheel into dist/
make check                    # twine check dist/*
make publish                  # twine upload — requires explicit user approval
```

Integration tests call real paid APIs. They are skipped unless you opt in twice: the `slow`
marker in `tests/conftest.py` needs `--run-slow`, and the credential check needs
`GENIMG_RUN_INTEGRATION_TESTS=1`.

```bash
GENIMG_RUN_INTEGRATION_TESTS=1 .venv/bin/pytest -m integration --run-slow
```

## Conventions

- Python 3.10+ syntax. Built-in generics: `list[str]`, `dict[str, Any]`.
- Type hints on every function. `mypy` runs with `disallow_untyped_defs`.
- Line length 100. **`ruff format` is the only formatter** and `ruff check` is the only linter.
  This matches `make format`, `make lint`, and the pre-commit hooks. The ruff pin in
  `requirements-dev.txt` and the `ruff-pre-commit` rev are kept in step so both agree.
- Tests: `tests/unit/` mocks all external services. `tests/integration/` hits real APIs and is
  opt-in. Name tests as behavior statements. Mark with `unit`, `integration`, or `slow`.
- Docs on change: `docs/CHANGELOG.md` (Keep a Changelog, Unreleased section),
  `docs/DECISIONS.md` for architecture choices, `README.md` for user-facing features.
- Version bumps touch `pyproject.toml`, the "Current version" line in `README.md`,
  `docs/CHANGELOG.md`, and `docs/releases/vX.Y.Z.md`. SemVer.

## Constraints

- **Public API boundary.** CLI and UI import only from the `genimg` root. Never import
  `genimg.core.*` or `genimg.utils.*` from `src/genimg/cli/` or `src/genimg/ui/`.
- **Error hierarchy.** Raise types from `genimg.utils.exceptions`, never bare `Exception`.
  Exit codes: 0 success, 2 validation/config, 1 API/network, 130 cancellation.
- **Do not hand-edit vendored or generated code:**
  `src/genimg/core/image_analysis/backends/_joytag_models.py`,
  `src/genimg/contrib/draw_things_poc/generated/`, and the checked-in `*_pb2*.py` gRPC stubs.
  Regenerate via `tools/draw_things_codegen/regen.sh` and keep `grpcio`/`protobuf` versions
  aligned with the stubs.
- **Secrets.** `.env` is gitignored and holds API keys. Never commit credentials or print them.
  `.env.example` is the reference for supported variables.
- **Coverage floor is enforced** at 80% (`--cov-fail-under=80` in `pyproject.toml`). Unit tests
  must not touch the network.
- **Do not commit** generated images (`*.png`, `*.webp`, …), `tmp/`, or `_local_docs/`.
