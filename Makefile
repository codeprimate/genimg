.PHONY: help install install-dev format lint typecheck test test-unit test-integration coverage clean check

help:
	@echo "Available commands:"
	@echo "  make install       - Install package in development mode"
	@echo "  make install-dev   - Install with development dependencies"
	@echo "  make format        - Format code with black"
	@echo "  make lint          - Lint code with ruff"
	@echo "  make typecheck     - Type check with mypy"
	@echo "  make test          - Run all tests"
	@echo "  make test-unit     - Run unit tests only"
	@echo "  make test-integration - Run integration tests only"
	@echo "  make coverage      - Run tests with coverage report"
	@echo "  make clean         - Remove build artifacts"
	@echo "  make check         - Run all quality checks (format, lint, typecheck, test)"

install:
	pip install -e .

install-dev:
	pip install -e .
	pip install -r requirements-dev.txt

format:
	black src/ tests/

lint:
	ruff check --fix src/ tests/

typecheck:
	mypy src/

test:
	pytest

test-unit:
	pytest -m unit

test-integration:
	.venv/bin/pytest -m integration --no-cov

coverage:
	pytest --cov-report=html
	@echo "Coverage report generated in htmlcov/index.html"

clean:
	rm -rf build/ dist/ *.egg-info/
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

check: format lint typecheck test
	@echo "All quality checks passed!"
