"""Unit tests for logging configuration."""

import logging
import os
from unittest.mock import patch

import pytest

from genimg.logging_config import (
    configure_logging,
    get_logger,
    get_verbosity_from_env,
    log_prompts,
    set_verbosity,
)


@pytest.mark.unit
class TestSetVerbosity:
    """Test set_verbosity level and log_prompts flag."""

    def test_level_0_sets_info_no_prompts(self):
        set_verbosity(0)
        root = logging.getLogger("genimg")
        assert root.level == logging.INFO
        assert log_prompts() is False

    def test_level_1_sets_info_with_prompts(self):
        set_verbosity(1)
        root = logging.getLogger("genimg")
        assert root.level == logging.INFO
        assert log_prompts() is True

    def test_level_2_sets_debug_with_prompts(self):
        set_verbosity(2)
        root = logging.getLogger("genimg")
        assert root.level == logging.DEBUG
        assert log_prompts() is True

    def test_negative_treated_as_default(self):
        set_verbosity(-1)
        root = logging.getLogger("genimg")
        assert root.level == logging.INFO
        assert log_prompts() is False


@pytest.mark.unit
class TestConfigureLogging:
    """Test configure_logging with quiet and verbose_level."""

    def test_quiet_sets_warning_and_no_prompts(self):
        set_verbosity(1)  # ensure log_prompts was True
        configure_logging(verbose_level=1, quiet=True)
        root = logging.getLogger("genimg")
        assert root.level == logging.WARNING
        assert log_prompts() is False

    def test_not_quiet_delegates_to_set_verbosity(self):
        configure_logging(verbose_level=2, quiet=False)
        root = logging.getLogger("genimg")
        assert root.level == logging.DEBUG
        assert log_prompts() is True


@pytest.mark.unit
class TestGetVerbosityFromEnv:
    """Test GENIMG_VERBOSITY parsing."""

    def test_default_missing(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GENIMG_VERBOSITY", None)
            assert get_verbosity_from_env() == 0

    def test_env_0(self):
        with patch.dict(os.environ, {"GENIMG_VERBOSITY": "0"}, clear=False):
            assert get_verbosity_from_env() == 0

    def test_env_1(self):
        with patch.dict(os.environ, {"GENIMG_VERBOSITY": "1"}, clear=False):
            assert get_verbosity_from_env() == 1

    def test_env_2(self):
        with patch.dict(os.environ, {"GENIMG_VERBOSITY": "2"}, clear=False):
            assert get_verbosity_from_env() == 2

    def test_invalid_falls_back_to_0(self):
        with patch.dict(os.environ, {"GENIMG_VERBOSITY": "x"}, clear=False):
            assert get_verbosity_from_env() == 0
        with patch.dict(os.environ, {"GENIMG_VERBOSITY": ""}, clear=False):
            assert get_verbosity_from_env() == 0


@pytest.mark.unit
class TestGetLogger:
    """Test get_logger returns child loggers under genimg."""

    def test_returns_genimg_child(self):
        log = get_logger("core.image_gen")
        assert log.name == "genimg.core.image_gen"

    def test_full_name_unchanged(self):
        log = get_logger("genimg.core.prompt")
        assert log.name == "genimg.core.prompt"

    def test_root_name_unchanged(self):
        log = get_logger("genimg")
        assert log.name == "genimg"
