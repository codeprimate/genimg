"""
Command-line interface for genimg.

This package contains CLI implementations using Click.
Uses only the public API: from genimg import ...
"""

from genimg.cli.commands import cli, main

__all__ = ["cli", "main"]
