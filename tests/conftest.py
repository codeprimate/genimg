"""
Pytest configuration: default runs most tests; use --run-slow to include slow tests.
"""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run slow tests (Florence describe, Ollama, OpenRouter). Default: skip them.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-slow", False):
        return
    skip_slow = pytest.mark.skip(reason="Slow test; run with --run-slow to include")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
