"""Unit tests for prompts_loader (YAML-loaded prompt templates)."""

import pytest

from genimg.core.prompts_loader import (
    get_optimization_template,
    get_prompt,
)


@pytest.mark.unit
class TestPromptsLoader:
    def test_get_optimization_template_returns_string_with_placeholder(self):
        template = get_optimization_template()
        assert isinstance(template, str)
        assert "{original_prompt}" in template
        assert "enhance" in template.lower()

    def test_get_prompt_optimization_template(self):
        template = get_prompt("optimization", "template")
        assert template is not None
        assert "{original_prompt}" in template

    def test_get_prompt_unknown_key_returns_none(self):
        assert get_prompt("nonexistent_key") is None
        assert get_prompt("optimization", "nonexistent_subkey") is None
