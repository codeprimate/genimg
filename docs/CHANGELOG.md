# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- (none)

### Changed
- Default logging verbosity (`GENIMG_VERBOSITY=0` / unset): `genimg` logger level is now **WARNING**, so routine **INFO** lines are not printed by default. Use `-v`, `GENIMG_VERBOSITY=1`, or `set_verbosity(1)` for previous default-style INFO logs (including prompts).

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

### Added
- Support for multiple image generation providers (Ollama and OpenRouter); CLI `--provider` option; provider-specific model loading in Gradio.
- AI process rules for specification, planning, execution, and release notes (`.cursor/rules`).
- Temporary path cleanup in Gradio app.

### Changed
- Gradio app text for image generation models (clarity).

## [0.9.6] - 2026-02-09

### Added
- Debug API logging (verbose/debug logging for API and cache).
- Image resizing with aspect ratio support.

### Changed
- Image processing configuration and validation improvements.

## [0.9.4] - 2026-02-07

### Changed
- Optimized prompt handling in Gradio app; enhanced output image display. DEVELOPMENT.md documentation updates.

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

### Changed
- (none)

### Fixed
- (none)

---

## Version History

### [0.1.0] - TBD

Initial release with:
- Core functionality for image generation
- Prompt optimization via Ollama
- Reference image support
- Configuration management
- Custom exception handling
- In-memory caching
- Comprehensive documentation

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
3. Update version in `src/genimg/__init__.py` and `pyproject.toml`
