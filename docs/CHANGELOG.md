# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project structure with src/ layout
- Core modules for configuration, prompt handling, image generation, and reference images
- Utility modules for caching and custom exceptions
- Virtual environment setup (.venv/)
- Comprehensive configuration via pyproject.toml
- Requirements files for core and development dependencies
- Complete documentation suite (README, AGENT, DECISIONS, DEVELOPMENT, EXAMPLES, CHANGELOG, PROJECT_INIT)
- Makefile for development tasks
- Pre-commit hooks configuration
- Environment variable template (.env.example)
- Entry point and CLI stub: `genimg` console script and `genimg generate` (Click); `__main__.py` for `python -m genimg`
- `genimg-ui` console script stub (prints "not yet implemented")
- Unit test suite: 107 tests, ~91% coverage (config, prompt, image_gen, reference, cache, exceptions, prompts_loader)
- Code review document (docs/CODE_REVIEW.md) and foundation sanity-check before CLI implementation

### Changed
- Prompt templates (e.g. optimization) are loaded from `src/genimg/prompts.yaml` instead of being hardcoded in `prompt.py`

### Fixed
- N/A (initial release)

### Known Issues
- Gradio UI not yet implemented (stub exits with message)
- Full CLI behavior not yet implemented (`genimg generate` is a stub; wiring to library pending)
- Cancellation supported via optional `cancel_check` on `optimize_prompt` / `generate_image` (see DECISIONS ADR-010)
- Development scripts and sample data not yet created

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
