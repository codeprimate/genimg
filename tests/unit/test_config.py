"""Unit tests for config."""

import os
from unittest.mock import patch

import pytest

from genimg.core.config import Config, get_config, set_config
from genimg.utils.exceptions import ConfigurationError


@pytest.mark.unit
class TestConfig:
    def test_validate_raises_when_no_api_key(self):
        c = Config(openrouter_api_key="")
        with pytest.raises(ConfigurationError) as exc_info:
            c.validate()
        assert "API key" in str(exc_info.value)

    def test_validate_raises_when_api_key_bad_prefix(self):
        c = Config(openrouter_api_key="invalid")
        with pytest.raises(ConfigurationError) as exc_info:
            c.validate()
        assert "sk-" in str(exc_info.value)

    def test_validate_sets_validated(self):
        c = Config(openrouter_api_key="sk-valid-key")
        c.validate()
        assert c.is_valid() is True

    def test_repr_does_not_contain_api_key(self):
        c = Config(openrouter_api_key="sk-secret")
        r = repr(c)
        assert "sk-secret" not in r
        assert "openrouter_api_key" not in r or "sk-" not in r

    def test_from_env_uses_env_vars(self):
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "sk-from-env",
                "GENIMG_DEFAULT_MODEL": "custom/model",
                "GENIMG_OPTIMIZATION_MODEL": "custom-ollama",
                "GENIMG_MIN_IMAGE_PIXELS": "5000",
            },
            clear=False,
        ):
            c = Config.from_env()
        assert c.openrouter_api_key == "sk-from-env"
        assert c.default_image_model == "custom/model"
        assert c.default_optimization_model == "custom-ollama"
        assert c.min_image_pixels == 5000

    def test_from_env_defaults_when_env_empty(self):
        with patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": ""},
            clear=False,
        ):
            c = Config.from_env()
        assert c.openrouter_api_key == ""
        assert "google" in c.default_image_model or c.default_image_model
        assert "llama" in c.default_optimization_model or c.default_optimization_model

    def test_from_env_min_image_pixels_default(self):
        with patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": "sk-ok"},
            clear=False,
        ):
            env = dict(os.environ)
            env.pop("GENIMG_MIN_IMAGE_PIXELS", None)
            with patch.dict(os.environ, env):
                c = Config.from_env()
        assert c.min_image_pixels == 2500

    def test_validate_raises_when_min_image_pixels_non_positive(self):
        c = Config(openrouter_api_key="sk-ok", min_image_pixels=0)
        with pytest.raises(ConfigurationError) as exc_info:
            c.validate()
        assert "min_image_pixels" in str(exc_info.value)

    def test_validate_raises_when_min_image_pixels_exceeds_max(self):
        c = Config(
            openrouter_api_key="sk-ok",
            min_image_pixels=3_000_000,
            max_image_pixels=2_000_000,
        )
        with pytest.raises(ConfigurationError) as exc_info:
            c.validate()
        assert "min_image_pixels" in str(exc_info.value)
        assert "max_image_pixels" in str(exc_info.value)

    def test_aspect_ratio_default(self):
        c = Config(openrouter_api_key="sk-ok")
        assert c.aspect_ratio == (1, 1)

    def test_validate_raises_when_aspect_ratio_non_positive(self):
        c = Config(openrouter_api_key="sk-ok", aspect_ratio=(0, 1))
        with pytest.raises(ConfigurationError) as exc_info:
            c.validate()
        assert "aspect_ratio" in str(exc_info.value)
        c2 = Config(openrouter_api_key="sk-ok", aspect_ratio=(1, 0))
        with pytest.raises(ConfigurationError) as exc_info2:
            c2.validate()
        assert "aspect_ratio" in str(exc_info2.value)

    def test_set_api_key_empty_raises(self):
        c = Config(openrouter_api_key="sk-ok")
        with pytest.raises(ConfigurationError):
            c.set_api_key("")
        assert c.openrouter_api_key == "sk-ok"

    def test_set_api_key_bad_prefix_raises(self):
        c = Config(openrouter_api_key="sk-ok")
        with pytest.raises(ConfigurationError):
            c.set_api_key("bad")
        assert c.openrouter_api_key == "sk-ok"

    def test_set_api_key_success_clears_validated(self):
        c = Config(openrouter_api_key="sk-old")
        c.validate()
        c.set_api_key("sk-new")
        assert c.openrouter_api_key == "sk-new"
        assert c.is_valid() is False

    def test_set_image_model_empty_raises(self):
        c = Config()
        with pytest.raises(ConfigurationError):
            c.set_image_model("")
        assert c.default_image_model != ""

    def test_set_image_model_no_slash_raises(self):
        c = Config()
        with pytest.raises(ConfigurationError):
            c.set_image_model("nomodel")
        assert "/" in (c.default_image_model or "")

    def test_set_image_model_success(self):
        c = Config()
        c.set_image_model("provider/name")
        assert c.default_image_model == "provider/name"

    def test_set_optimization_model_empty_raises(self):
        c = Config()
        with pytest.raises(ConfigurationError):
            c.set_optimization_model("")
        assert c.default_optimization_model != ""

    def test_set_optimization_model_success(self):
        c = Config()
        c.set_optimization_model("llama3")
        assert c.default_optimization_model == "llama3"


@pytest.mark.unit
class TestConfigGlobals:
    def test_set_config_then_get_config_returns_set(self):
        from genimg.core import config as config_mod

        c = Config(openrouter_api_key="sk-set")
        set_config(c)
        try:
            cfg = get_config()
            assert cfg is c
            assert cfg.openrouter_api_key == "sk-set"
        finally:
            config_mod._global_config = None

    def test_get_config_calls_from_env_when_global_none(self):
        from genimg.core import config as config_mod

        with patch.object(Config, "from_env") as from_env:
            from_env.return_value = Config(openrouter_api_key="sk-stub")
            orig = config_mod._global_config
            config_mod._global_config = None
            try:
                cfg = get_config()
                assert cfg.openrouter_api_key == "sk-stub"
                from_env.assert_called_once()
            finally:
                config_mod._global_config = orig
