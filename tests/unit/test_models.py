"""Unit tests for models loader (YAML-loaded default model IDs)."""

from unittest.mock import mock_open, patch

import pytest
import yaml

from genimg.core.models import (
    _load_models,
    default_image_model,
    default_ollama_image_model,
    default_optimization_model,
    image_models,
    merge_optimization_model_choices,
)
from genimg.utils.exceptions import ConfigurationError


@pytest.mark.unit
class TestModelsLoader:
    def test_defaults_match_bundled_yaml(self):
        assert default_image_model() == "bytedance-seed/seedream-4.5"
        assert default_ollama_image_model() == "x/z-image-turbo"
        assert default_optimization_model() == "huihui_ai/qwen3.5-abliterated:4b"

    def test_image_models_is_non_empty_list(self):
        models = image_models()
        assert isinstance(models, list)
        assert len(models) > 0
        assert default_image_model() in models


@pytest.mark.unit
class TestMergeOptimizationModelChoices:
    def test_merges_default_and_installed_with_default_first(self):
        choices = merge_optimization_model_choices(
            default="custom/default",
            installed=["llama3.2", "mistral:7b"],
        )
        assert choices[0] == "custom/default"
        assert "llama3.2" in choices
        assert "mistral:7b" in choices

    def test_deduplicates_across_sources(self):
        default = default_optimization_model()
        choices = merge_optimization_model_choices(
            default=default,
            installed=[default, "llama3.2"],
        )
        assert choices.count(default) == 1
        assert choices[0] == default


@pytest.mark.unit
class TestModelsYAMLValidation:
    def setup_method(self):
        import genimg.core.models as models_mod

        models_mod._models_data = None

    def test_malformed_yaml_raises_configuration_error(self):
        import genimg.core.models as models_mod

        models_mod._models_data = None
        invalid_yaml = "default_image_model: [\nbad"

        with patch("importlib.resources.files") as mock_files:
            mock_file = mock_open(read_data=invalid_yaml)
            mock_files.return_value.joinpath.return_value.open.return_value = mock_file()

            with pytest.raises(ConfigurationError) as exc_info:
                _load_models()

            assert "Failed to parse models.yaml" in str(exc_info.value)

    def test_missing_required_keys_raises_configuration_error(self):
        import genimg.core.models as models_mod

        models_mod._models_data = None
        data = {"image_models": ["a/b"]}

        with patch("importlib.resources.files") as mock_files:
            mock_file = mock_open(read_data=yaml.dump(data))
            mock_files.return_value.joinpath.return_value.open.return_value = mock_file()

            with pytest.raises(ConfigurationError) as exc_info:
                _load_models()

            assert "Invalid models.yaml structure" in str(exc_info.value)
