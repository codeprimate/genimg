"""Unit tests for prompts_loader (YAML-loaded prompt templates)."""

from unittest.mock import mock_open, patch

import pytest
import yaml

from genimg.core.prompts_loader import (
    _load_prompts,
    get_optimization_template,
    get_prompt,
)
from genimg.utils.exceptions import ConfigurationError


@pytest.mark.unit
class TestPromptsLoader:
    def test_get_optimization_template_returns_string_with_placeholder(self):
        template = get_optimization_template()
        assert isinstance(template, str)
        assert "{reference_image_instruction}" in template
        assert "scene" in template.lower()

    def test_get_prompt_optimization_template(self):
        template = get_prompt("optimization", "template")
        assert template is not None
        assert "{reference_image_instruction}" in template

    def test_get_prompt_unknown_key_returns_none(self):
        assert get_prompt("nonexistent_key") is None
        assert get_prompt("optimization", "nonexistent_subkey") is None


@pytest.mark.unit
class TestYAMLValidation:
    """Test YAML validation with Pydantic schema."""

    def setup_method(self):
        """Clear the module-level cache before each test."""
        import genimg.core.prompts_loader

        genimg.core.prompts_loader._prompts_data = None

    def test_valid_yaml_loads_successfully(self):
        """Valid YAML with required structure should load without errors."""
        # Use actual prompts.yaml which should be valid
        data = _load_prompts()
        assert "optimization" in data
        assert "template" in data["optimization"]

    def test_malformed_yaml_raises_configuration_error(self):
        """Malformed YAML should raise ConfigurationError with helpful message."""
        import genimg.core.prompts_loader

        genimg.core.prompts_loader._prompts_data = None

        invalid_yaml = "optimization:\n  template: |\n    foo\n  bar:\nbad indentation"

        with patch("importlib.resources.files") as mock_files:
            mock_file = mock_open(read_data=invalid_yaml)
            mock_files.return_value.joinpath.return_value.open.return_value = mock_file()

            with pytest.raises(ConfigurationError) as exc_info:
                _load_prompts()

            assert "Failed to parse prompts.yaml" in str(exc_info.value)

    def test_empty_yaml_raises_configuration_error(self):
        """Empty YAML file should raise ConfigurationError."""
        import genimg.core.prompts_loader

        genimg.core.prompts_loader._prompts_data = None

        with patch("importlib.resources.files") as mock_files:
            mock_file = mock_open(read_data="")
            mock_files.return_value.joinpath.return_value.open.return_value = mock_file()

            with pytest.raises(ConfigurationError) as exc_info:
                _load_prompts()

            assert "empty" in str(exc_info.value).lower()

    def test_missing_required_keys_raises_configuration_error(self):
        """YAML without required 'optimization.template' should raise ConfigurationError."""
        import genimg.core.prompts_loader

        genimg.core.prompts_loader._prompts_data = None

        # Valid YAML but missing required structure
        invalid_structure = yaml.dump({"some_other_key": "value"})

        with patch("importlib.resources.files") as mock_files:
            mock_file = mock_open(read_data=invalid_structure)
            mock_files.return_value.joinpath.return_value.open.return_value = mock_file()

            with pytest.raises(ConfigurationError) as exc_info:
                _load_prompts()

            error_msg = str(exc_info.value)
            assert "Invalid prompts.yaml structure" in error_msg
            assert "optimization" in error_msg

    def test_file_not_found_raises_configuration_error(self):
        """Missing prompts.yaml file should raise ConfigurationError."""
        import genimg.core.prompts_loader

        genimg.core.prompts_loader._prompts_data = None

        with patch("importlib.resources.files") as mock_files:
            mock_files.return_value.joinpath.return_value.open.side_effect = FileNotFoundError

            with pytest.raises(ConfigurationError) as exc_info:
                _load_prompts()

            assert "prompts.yaml not found" in str(exc_info.value)

    def test_caching_prevents_revalidation(self):
        """Second call to _load_prompts should use cache without revalidation."""
        import genimg.core.prompts_loader

        # First load
        _load_prompts()
        assert genimg.core.prompts_loader._prompts_data is not None

        # Modify the cache
        original_cache = genimg.core.prompts_loader._prompts_data
        genimg.core.prompts_loader._prompts_data = {"test": "cached"}

        # Second load should return cached value
        data2 = _load_prompts()
        assert data2 == {"test": "cached"}

        # Restore for other tests
        genimg.core.prompts_loader._prompts_data = original_cache
