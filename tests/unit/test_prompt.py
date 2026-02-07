"""Unit tests for prompt validation and optimization (mocked)."""

from unittest.mock import MagicMock, patch

import pytest

from genimg.core.config import Config
from genimg.core.prompt import (
    OPTIMIZATION_TEMPLATE,
    check_ollama_available,
    optimize_prompt,
    optimize_prompt_with_ollama,
    validate_prompt,
)
from genimg.utils.cache import get_cache
from genimg.utils.exceptions import APIError, CancellationError, RequestTimeoutError, ValidationError


@pytest.mark.unit
class TestValidatePrompt:
    def test_empty_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_prompt("")
        assert exc_info.value.field == "prompt"

    def test_whitespace_only_raises(self):
        with pytest.raises(ValidationError):
            validate_prompt("   \n  ")

    def test_too_short_raises(self):
        with pytest.raises(ValidationError):
            validate_prompt("ab")

    def test_valid_passes(self):
        validate_prompt("a red car")
        validate_prompt("yes")  # at least 3 chars


@pytest.mark.unit
class TestCheckOllamaAvailable:
    def test_returns_true_when_ollama_list_succeeds(self):
        with patch("genimg.core.prompt.subprocess.run") as m:
            m.return_value = MagicMock(returncode=0)
            assert check_ollama_available() is True
            m.assert_called_once()
            assert m.call_args[0][0] == ["ollama", "list"]

    def test_returns_false_when_ollama_list_fails(self):
        with patch("genimg.core.prompt.subprocess.run") as m:
            m.return_value = MagicMock(returncode=1)
            assert check_ollama_available() is False

    def test_returns_false_on_filenotfound(self):
        with patch("genimg.core.prompt.subprocess.run") as m:
            m.side_effect = FileNotFoundError()
            assert check_ollama_available() is False

    def test_returns_false_on_timeout(self):
        import subprocess

        with patch("genimg.core.prompt.subprocess.run") as m:
            m.side_effect = subprocess.TimeoutExpired("ollama", 5)
            assert check_ollama_available() is False


@pytest.mark.unit
class TestOptimizePrompt:
    def test_optimization_disabled_returns_original(self):
        config = Config(openrouter_api_key="sk-x", optimization_enabled=False)
        result = optimize_prompt("a red car", config=config)
        assert result == "a red car"

    def test_cache_hit_returns_cached_without_ollama(self):
        cache = get_cache()
        cache.clear()
        cache.set("red car", "llama3.2", "optimized red car")
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=False):
            result = optimize_prompt("red car", config=config, enable_cache=True)
        assert result == "optimized red car"
        cache.clear()

    def test_cache_miss_raises_when_ollama_unavailable(self):
        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=False):
            with pytest.raises(APIError) as exc_info:
                optimize_prompt("unknown prompt", config=config, enable_cache=True)
        assert "Ollama" in str(exc_info.value)
        cache.clear()

    def test_optimize_prompt_with_ollama_success_and_caches(self):
        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.Popen") as Popen:
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate.return_value = ("  enhanced prompt  \n", "")
                Popen.return_value = proc
                result = optimize_prompt("original", config=config, enable_cache=True)
        assert result == "enhanced prompt"
        assert cache.get("original", config.default_optimization_model, None) == "enhanced prompt"
        cache.clear()

    def test_optimize_prompt_with_ollama_cache_hit_returns_cached(self):
        cache = get_cache()
        cache.clear()
        cache.set("cached", "llama3.2", "from cache")
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.Popen") as Popen:
                result = optimize_prompt_with_ollama("cached", config=config)
        assert result == "from cache"
        Popen.assert_not_called()
        cache.clear()

    def test_optimize_prompt_with_ollama_timeout_raises(self):
        import subprocess

        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.Popen") as Popen:
                proc = MagicMock()
                proc.communicate.side_effect = subprocess.TimeoutExpired("ollama", 10)
                proc.kill = MagicMock()
                Popen.return_value = proc
                with pytest.raises(RequestTimeoutError):
                    optimize_prompt_with_ollama("long prompt", config=config, timeout=10)
        cache.clear()

    def test_optimize_prompt_with_ollama_nonzero_return_raises(self):
        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.Popen") as Popen:
                proc = MagicMock()
                proc.returncode = 1
                proc.communicate.return_value = ("", "error message")
                Popen.return_value = proc
                with pytest.raises(APIError) as exc_info:
                    optimize_prompt_with_ollama("abc", config=config)
        assert "error message" in str(exc_info.value)
        cache.clear()

    def test_optimize_prompt_with_ollama_empty_stdout_raises(self):
        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.Popen") as Popen:
                proc = MagicMock()
                proc.returncode = 0
                proc.communicate.return_value = ("   \n", "")
                Popen.return_value = proc
                with pytest.raises(APIError) as exc_info:
                    optimize_prompt_with_ollama("abc", config=config)
        assert "empty" in str(exc_info.value).lower()
        cache.clear()

    def test_optimize_prompt_with_ollama_filenotfound_raises(self):
        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.Popen") as Popen:
                Popen.side_effect = FileNotFoundError()
                with pytest.raises(APIError) as exc_info:
                    optimize_prompt_with_ollama("abc", config=config)
        assert "not found" in str(exc_info.value).lower() or "PATH" in str(exc_info.value)
        cache.clear()

    def test_optimization_template_contains_placeholder(self):
        assert "{original_prompt}" in OPTIMIZATION_TEMPLATE
        assert "enhance" in OPTIMIZATION_TEMPLATE.lower()

    def test_cancel_check_raises_cancellation_error(self):
        """When cancel_check returns True, optimization is cancelled and process is terminated."""
        import time

        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        call_count = [0]

        def cancel_after_two():
            call_count[0] += 1
            return call_count[0] >= 2

        def blocking_communicate(*args, **kwargs):
            time.sleep(2)  # Block so main thread can poll and cancel
            return ("", "")

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.Popen") as Popen:
                proc = MagicMock()
                proc.communicate = blocking_communicate
                proc.returncode = 0
                proc.terminate = MagicMock()
                Popen.return_value = proc
                with pytest.raises(CancellationError) as exc_info:
                    optimize_prompt_with_ollama(
                        "original", config=config, cancel_check=cancel_after_two
                    )
        assert "cancelled" in str(exc_info.value).lower()
        proc.terminate.assert_called_once()
        cache.clear()
