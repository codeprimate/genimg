# PROJECT_INIT.md - Project Initialization Template

This document captures the initialization process for genimg and serves as a **reusable template** for future Python projects.

## Overview

This template documents the decisions, structure, and process used to initialize the genimg project. Copy this file to new projects and customize as needed.

## Planning Phase Decisions

These questions were answered during planning:

| Question | Decision | Notes |
|----------|----------|-------|
| **Package name** | genimg | Short, descriptive |
| **Project structure** | src/ layout | Modern best practice |
| **Interfaces** | CLI + Web UI + Library | Maximum flexibility |
| **Testing framework** | pytest | Industry standard |
| **Build tool** | pyproject.toml | PEP 517/518 compliant |
| **Virtual environment** | venv | Standard library |
| **Python version** | >=3.8 | Wide compatibility |
| **Code formatter** | black | Opinionated, consistent |
| **Linter** | ruff | Fast, comprehensive |
| **Type checker** | mypy | Strict mode |

## Project Structure Template

```
project_name/
├── Configuration
│   ├── .gitignore
│   ├── .env.example
│   ├── .pre-commit-config.yaml (optional)
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── Makefile
├── Documentation
│   ├── README.md
│   ├── SPEC.md (if separate from README)
│   ├── AGENT.md
│   ├── DECISIONS.md
│   ├── DEVELOPMENT.md
│   ├── EXAMPLES.md
│   ├── CHANGELOG.md
│   └── PROJECT_INIT.md (this file)
├── Source Code
│   └── src/
│       └── project_name/
│           ├── __init__.py
│           ├── __main__.py
│           ├── core/
│           ├── ui/
│           ├── cli/
│           └── utils/
├── Tests
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       ├── integration/
│       └── fixtures/
├── Development Tools
│   └── scripts/
│       ├── test_*.py
│       └── other utilities
└── Sample Data
    └── docs/
        └── samples/
```

## Documentation Standards

### README.md
- Installation instructions (venv, dependencies)
- Quick start examples (CLI, UI, library)
- Configuration (environment variables)
- Basic usage examples
- Links to detailed docs

### SPEC.md
- Full functional specification
- User workflows
- Requirements
- Data structures
- Integration points

### AGENT.md
- Project architecture overview
- Module responsibilities
- Coding patterns and practices
- Testing strategy
- Development workflow
- Gotchas and lessons learned
- Dependencies and their purposes

### DECISIONS.md
- Architecture Decision Records (ADRs)
- Each decision includes:
  - Date, Decision, Context, Options, Rationale, Consequences
- Prevents relitigating solved problems
- Provides historical context

### DEVELOPMENT.md
- Setup instructions
- Common development tasks
- Testing guide
- Debugging guide
- Performance considerations
- Release process

### EXAMPLES.md
- Working code examples
- API request/response samples
- Before/after examples
- Error handling patterns
- Testing examples

### CHANGELOG.md
- Track changes between sessions
- Follow Keep a Changelog format
- Known issues section
- Version history

### PROJECT_INIT.md
- This template
- Captures initialization process
- Updated with lessons learned

## Code Quality Setup

### Tool Configuration in pyproject.toml

```toml
[tool.black]
line-length = 100
target-version = ["py38", "py39", "py310", "py311"]

[tool.ruff]
target-version = "py38"
line-length = 100
select = ["E", "W", "F", "I", "N", "UP", "B", "C4", "PTH", "SIM", "TID"]

[tool.mypy]
python_version = "3.8"
warn_return_any = true
disallow_untyped_defs = true
strict_equality = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = ["--strict-markers", "--cov=src/project_name", "--cov-fail-under=80"]
markers = ["unit: Unit tests", "integration: Integration tests", "slow: Slow tests"]
```

### Makefile

Standard commands:
- `make install` - Install package
- `make install-dev` - Install with dev dependencies
- `make format` - Format code
- `make lint` - Lint code
- `make typecheck` - Type check
- `make test` - Run tests
- `make coverage` - Coverage report
- `make check` - All quality checks

## Testing Strategy

### Test Organization
- `tests/unit/` - Mock all external dependencies
- `tests/integration/` - Test component interactions
- `tests/fixtures/` - Shared test data

### Coverage Targets
- Overall: >80%
- Critical modules (security, core logic): >95%
- Exception handling: 100%

### Pytest Fixtures
- Config fixtures
- Mock API responses
- Sample data files
- Temporary directories

## Development Scripts

Create in `scripts/` directory:
- `test_api.py` - Validate external API connection
- `test_*.py` - Validate other dependencies
- `benchmark.py` - Performance testing
- `inspect_*.py` - Debug internal state

## Sample Data

Create in `docs/samples/`:
- Example inputs
- Example outputs
- API response samples
- Before/after examples

## Initial TODO Checklist

### Phase 1: Foundation
- [ ] Create virtual environment
- [ ] Create .gitignore
- [ ] Create directory structure
- [ ] Create pyproject.toml
- [ ] Create requirements files

### Phase 2: Core Implementation
- [ ] Create __init__.py files
- [ ] Implement core modules
- [ ] Implement user interfaces
- [ ] Create entry points

### Phase 3: Testing
- [ ] Create test structure
- [ ] Create fixtures
- [ ] Write unit tests
- [ ] Write integration tests

### Phase 4: Quality
- [ ] Configure linting tools
- [ ] Create Makefile
- [ ] Create pre-commit config (optional)

### Phase 5: Documentation
- [ ] Write README.md
- [ ] Write AGENT.md
- [ ] Write DECISIONS.md
- [ ] Write DEVELOPMENT.md
- [ ] Write EXAMPLES.md
- [ ] Write CHANGELOG.md
- [ ] Write PROJECT_INIT.md
- [ ] Create .env.example
- [ ] Create sample data

### Phase 6: Verification
- [ ] Install in venv
- [ ] Run all tests
- [ ] Run all linters
- [ ] Generate coverage report
- [ ] Test CLI commands
- [ ] Test UI (if applicable)

## Customization Guide

### What to Customize
- Package name throughout
- Module names (core/, ui/, cli/)
- Dependencies
- Entry point commands
- Testing fixtures
- Sample data
- API integrations

### What Stays Consistent
- Documentation structure
- Testing organization
- Code quality tools
- Development workflow
- Directory conventions

### When to Deviate
- Non-Python projects
- Library-only packages (no UI/CLI)
- Simple scripts (may not need full structure)
- Domain-specific requirements

## Lessons Learned

### What Worked Well
- ✅ Structured documentation from day 1
- ✅ Test structure before implementation
- ✅ Clear separation of concerns
- ✅ Type hints throughout
- ✅ Comprehensive configuration

### What Could Improve
- 📝 (To be filled during development)
- 📝 (Updated as issues are discovered)

### Gotchas Discovered
- 📝 (To be filled during development)
- 📝 (Project-specific issues)

### Best Practices Discovered
- 📝 (To be filled during development)
- 📝 (Patterns that worked well)

## Reuse Instructions

### For New Projects

1. **Copy this file** to new project directory
2. **Answer planning questions** at top of this document
3. **Create structure** using the template above
4. **Follow TODO checklist** in order
5. **Customize** as needed for project requirements
6. **Update lessons learned** as you discover them
7. **Update this template** with improvements

### Continuous Improvement

After completing a project:
1. Review what worked well
2. Document gotchas and solutions
3. Update template with improvements
4. Share learnings with team
5. Refine for next project

## Template Metadata

| Field | Value |
|-------|-------|
| **Template Version** | 1.0 |
| **Created For** | genimg |
| **Date** | 2026-02-06 |
| **Python Version** | 3.8+ |
| **Build System** | setuptools + pyproject.toml |
| **License** | MIT |

---

## Notes for Future Projects

This template captures the initialization process used for genimg. Key principles:

1. **Documentation First**: Write docs alongside code
2. **Test Early**: Set up testing infrastructure from start
3. **Quality Gates**: Configure linters and type checkers immediately
4. **Clear Structure**: Follow src/ layout and separate concerns
5. **AI-Friendly**: Document decisions and patterns for future agents

The goal is to create a consistent, high-quality foundation that accelerates development and reduces cognitive load for both humans and AI agents.
