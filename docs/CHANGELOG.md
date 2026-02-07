# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- (none)

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
