# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- (none)

### Changed
- (none)

## [0.12.0] - 2026-04-18

### Added
- CLI `--format` for `genimg generate` and `genimg character`: `png`, `jpg`, or `webp` (default `webp`). The final path extension always matches `--format` (including when `--out` / `--output` used a different suffix). JPEG and WebP embed best-effort EXIF (`Software`, `ImageDescription`, `UserComment` JSON mirroring the PNG `genimg` metadata schema).

### Changed
- **Breaking (CLI):** default on-disk output is **WebP** (lossy quality 95, `method=6`) instead of following the API wire format; scripts that assumed a `.png` default or raw API bytes should pass `--format png` or read the path printed on stdout.
- CLI saves always encode from `GenerationResult.image` for the chosen `--format`, not `image_data` verbatim (so non-PNG API responses still get CLI metadata when using JPEG/WebP, and `--format png` always uses the full PNG metadata pipeline).
- CLI WebP output now muxes an **XMP** chunk (`xmp:CreatorTool`, `tiff:Software`) and sets EXIF **ProcessingSoftware** (tag 11) alongside **Software** (305), so hosts that do not surface tag 305 as application metadata still see the genimg version string.

## [0.11.3] - 2026-04-18

### Changed
- PNG `Software` text metadata (CLI-saved outputs): value is now `genimg <version> (<provider>/<model>)` so viewers that only show standard fields still identify the backend; `Description` (final prompt) and the `genimg` JSON `iTXt` chunk are unchanged.

## [0.11.2] - 2026-04-18

### Added
- CLI (`genimg generate`, `genimg character`): PNG outputs embed standard text metadata (`Software` = `genimg <version>`, `Description` = final prompt) and an `iTXt` chunk `genimg` with JSON (`provider`, `model`, `generation_time_s`, `had_reference`, `optimized`, `cli`, `creation_time`, plus `original_prompt` when optimization ran, `user_prompt` for character when provided). JPEG outputs unchanged (raw bytes). `GenerationResult.image_data` remains metadata-free for API and scripts.

## [0.11.1] - 2026-04-18

### Changed
- PNG output: `GenerationResult.image_data` and reference image base64 encoding use Pillow **`optimize=True`** and **`compress_level=9`** for smaller lossless PNG files (slightly more CPU on encode).

## [0.11.0] - 2026-04-18

### Changed
- Default logging verbosity (`GENIMG_VERBOSITY=0` / unset): `genimg` logger level is now **WARNING**, so routine **INFO** lines are not printed by default. Use `-v`, `GENIMG_VERBOSITY=1`, or `set_verbosity(1)` for previous default-style INFO logs (including prompts).

## [0.10.6] - 2026-04-18

### Added
- CLI `genimg character` for turnaround-style sheets with **multiple reference images**; path-only stdout, stderr banner/summary, and progress integration.
- Library and providers: `reference_images_b64` on `generate_image` (legacy single `reference_image_b64` retained); OpenRouter payload uses text plus ordered `image_url` parts; safer multi-image debug logging.

### Changed
- Gradio app wired to pass reference images as a list; default image model / OpenRouter constraints aligned with character flow (see README).

## [0.10.5] - 2026-04-05

### Changed
- Prompt optimization: strip **ANSI escape sequences** from Ollama subprocess output so the terminal UI stays readable.

## [0.10.4] - 2026-03-18

### Added
- **`--optimize-thinking`** for prompt optimization (CLI); Gradio control and **`optimize_thinking`** in config / environment; optimization cache distinguishes thinking vs non-thinking entries.

### Fixed
- Makefile: `pip install` targets no longer prefix commands with a hard-coded virtualenv path.

## [0.10.3] - 2026-03-18

### Changed
- Default optimization model set to **`huihui_ai/qwen3.5-abliterated:4b`** (replacing the previous default); `.env.example`, README, examples, `ui_models.yaml`, and tests updated accordingly.

## [0.10.2] - 2026-02-25

### Changed
- **Dependencies**: raised floors/ranges for Pillow (12.x), Rich (14.x), PyTorch / torchvision, and related pins; `requirements.txt` kept in sync with `pyproject.toml`.

## [0.10.1] - 2026-02-24

### Added
- Browser notifications when image generation or prompt optimization completes (optional; permission requested on load).

### Changed
- Gradio app: improved temporary image path management; prompt normalization; optimization condition and output handling.

### Fixed
- Optimized prompt edits are now preserved when generation completes.

## [0.10.0] - 2026-02-21

### Added
- Startup message in Gradio app showing version.

### Changed
- Gradio app layout and reference image messaging; enhanced image description features. Functional specification updated to 1.2.

## [0.9.9] - 2026-02-18

### Changed
- Gradio app: dynamic page titles and version constraints; clearer prompt optimization guidelines and elaboration; refined default provider and configuration.

## [0.9.8] - 2026-02-16

### Changed
- Gradio app: clearer copy for image generation models.

### Fixed
- Gradio app: temporary path cleanup for generated assets.

## [0.9.7] - 2026-02-16

### Added
- **Multiple image generation providers** (Ollama and OpenRouter); CLI **`--provider`**; provider-specific model loading in Gradio.
- AI process rules for specification, planning, execution, and release notes (`.cursor/rules`).
- Debug API logging (verbose/debug logging for API and cache).
- Image resizing with **aspect ratio** support.

## [0.9.6] - 2026-02-09

### Added
- (none)

### Changed
- Image processing configuration and validation improvements.
- Gradio app: enhanced output image display.
- `DEVELOPMENT.md` documentation clarity.

## [0.9.4] - 2026-02-07

### Changed
- Gradio app: optimized prompt handling.

## [0.9.3] - 2026-02-07

### Added
- Gradio UI: logo integration and asset management.

### Changed
- Launch functionality in Gradio app; README updates for new features and enhancements.

## [0.9.2] - 2026-02-07

### Added
- Structured logging throughout the codebase. Default level shows activity and performance (e.g. "Generating image", "Optimized in X.Xs"); use `-v` to also log prompts, `-vv` for API/cache and other debug detail.
- CLI verbosity: `-v` / `--verbose` (repeatable: `-vv` for verbose). `--quiet` sets log level to WARNING (no activity/performance logs).
- Environment variable `GENIMG_VERBOSITY` (0, 1, or 2) for library and UI; CLI flags override.
- Library API: `set_verbosity(level)` and `configure_logging(verbose_level, quiet)` in `genimg` for controlling log level and prompt logging from Python.

## [0.9.1] - 2026-02-07

### Changed
- `.gitignore`: exclude local documentation directory; remove obsolete code review process document.
- Dependency management updates in packaging metadata.

## [0.9.0] - 2026-02-07

### Added
- YAML-backed prompt templates (`prompts.yaml`); configuration-driven image generation and prompt optimization; request timeout handling and improved image/cache utilities.
- CLI: **`--save-prompt`**, **`--list-models`**, API key override; cancellation support for generation and optimization.
- Gradio: layout refactors, optimization checkbox, dynamic tabs, status messaging, and broader image-generation UX.

### Changed
- Python requirement and default models updated; Makefile and dependencies refreshed; documentation and agent guidelines expanded.

---

## How to Update This File

When making changes, add entries under the "Unreleased" section in the appropriate category:

- **Added**: New features
- **Changed**: Changes to existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security fixes

When releasing a new version:
1. Change "Unreleased" to the version number and date
2. Add a new "Unreleased" section above it
3. Update version in `pyproject.toml` (package version is read from installed metadata via `importlib.metadata`)
