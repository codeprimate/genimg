"""Unit tests for prompt validation and optimization (mocked)."""

import warnings
from unittest.mock import MagicMock, patch

import pytest

from genimg.core.config import Config
from genimg.core.prompt import (
    OPTIMIZATION_TEMPLATE,
    _strip_ollama_thinking,
    check_ollama_available,
    list_ollama_models,
    optimize_prompt,
    optimize_prompt_with_ollama,
    validate_prompt,
)
from genimg.utils.cache import get_cache
from genimg.utils.exceptions import (
    APIError,
    CancellationError,
    RequestTimeoutError,
    ValidationError,
)


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
class TestStripOllamaThinking:
    """Test _strip_ollama_thinking (thinking models and markdown fences)."""

    def test_no_thinking_unchanged(self):
        assert _strip_ollama_thinking("a red car") == "a red car"
        assert _strip_ollama_thinking("  only prompt  ") == "only prompt"

    def test_strips_thinking_block(self):
        raw = "prelude Thinking... internal reasoning ...done thinking. the actual prompt"
        assert _strip_ollama_thinking(raw) == "prelude the actual prompt"

    def test_strips_thinking_with_no_end_keeps_before(self):
        raw = "the prompt Thinking... unfinished"
        assert _strip_ollama_thinking(raw) == "the prompt"

    def test_strips_markdown_fences(self):
        raw = "```\na red car\n```"
        assert _strip_ollama_thinking(raw) == "a red car"

    def test_strips_thinking_then_markdown(self):
        raw = "Thinking... blah ...done thinking.\n```\nfinal prompt\n```"
        assert _strip_ollama_thinking(raw) == "final prompt"

    def test_empty_or_whitespace_unchanged(self):
        assert _strip_ollama_thinking("") == ""
        assert _strip_ollama_thinking("   ") == "   "


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
class TestListOllamaModels:
    def test_returns_empty_list_when_ollama_not_available(self):
        with patch("genimg.core.prompt.check_ollama_available", return_value=False):
            assert list_ollama_models() == []

    def test_parses_ollama_list_output(self):
        output = """NAME                            ID              SIZE    MODIFIED
svjack/gpt-oss-20b-heretic:latest   abc123def456    10 GB   2 days ago
llama2:latest                   def456abc789    4 GB    1 week ago
mistral:7b                      ghi789jkl012    4 GB    3 days ago"""

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.run") as m:
                m.return_value = MagicMock(returncode=0, stdout=output)
                models = list_ollama_models()
                assert models == ["svjack/gpt-oss-20b-heretic", "llama2", "mistral:7b"]

    def test_strips_latest_tag(self):
        output = """NAME                    ID          SIZE    MODIFIED
model1:latest           abc123      5 GB    1 day ago
model2:v1               def456      3 GB    2 days ago"""

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.run") as m:
                m.return_value = MagicMock(returncode=0, stdout=output)
                models = list_ollama_models()
                assert models == ["model1", "model2:v1"]

    def test_returns_empty_list_on_nonzero_returncode(self):
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.run") as m:
                m.return_value = MagicMock(returncode=1, stdout="")
                assert list_ollama_models() == []

    def test_returns_empty_list_on_header_only(self):
        output = """NAME                    ID          SIZE    MODIFIED"""

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.run") as m:
                m.return_value = MagicMock(returncode=0, stdout=output)
                assert list_ollama_models() == []

    def test_handles_filenotfound(self):
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.run") as m:
                m.side_effect = FileNotFoundError()
                assert list_ollama_models() == []

    def test_handles_timeout(self):
        import subprocess

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.run") as m:
                m.side_effect = subprocess.TimeoutExpired("ollama", 5)
                assert list_ollama_models() == []


@pytest.mark.unit
class TestOptimizePrompt:
    def test_optimization_disabled_returns_original(self):
        config = Config(openrouter_api_key="sk-x", optimization_enabled=False)
        result = optimize_prompt("a red car", config=config)
        assert result == "a red car"

    def test_cache_hit_returns_cached_without_ollama(self):
        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        # Cache key must use same model as config.default_optimization_model for lookup to hit
        cache.set("red car", config.default_optimization_model, "optimized red car")
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
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        # Cache key must use same model as config.default_optimization_model for lookup to hit
        cache.set("cached", config.default_optimization_model, "from cache")
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
        assert "{reference_image_instruction}" in OPTIMIZATION_TEMPLATE
        assert (
            "visual scene architect" in OPTIMIZATION_TEMPLATE.lower()
            or "scene" in OPTIMIZATION_TEMPLATE.lower()
        )

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


@pytest.mark.unit
class TestSubprocessCleanup:
    """Test that subprocess cleanup properly waits for process termination."""

    def test_timeout_calls_wait_after_kill(self):
        """When timeout occurs, verify kill() is followed by wait()."""
        import subprocess

        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.Popen") as Popen:
                proc = MagicMock()
                proc.communicate.side_effect = subprocess.TimeoutExpired("ollama", 10)
                proc.kill = MagicMock()
                proc.wait = MagicMock()
                Popen.return_value = proc

                with pytest.raises(RequestTimeoutError):
                    optimize_prompt_with_ollama("test", config=config, timeout=10)

                # Verify both kill and wait were called
                proc.kill.assert_called_once()
                proc.wait.assert_called_once()
        cache.clear()

    def test_cancellation_calls_wait_after_terminate(self):
        """When cancelled, verify terminate() is followed by wait()."""
        import time

        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)

        def cancel_immediately():
            return True

        def blocking_communicate(*args, **kwargs):
            time.sleep(2)
            return ("result", "")

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.Popen") as Popen:
                proc = MagicMock()
                proc.communicate = blocking_communicate
                proc.terminate = MagicMock()
                proc.wait = MagicMock()
                Popen.return_value = proc

                with pytest.raises(CancellationError):
                    optimize_prompt_with_ollama(
                        "test", config=config, cancel_check=cancel_immediately
                    )

                # Verify both terminate and wait were called
                proc.terminate.assert_called_once()
                proc.wait.assert_called()
        cache.clear()

    def test_cancellation_kills_if_terminate_times_out(self):
        """If terminate() times out, verify kill() and wait() are called."""
        import subprocess
        import time

        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)

        def cancel_immediately():
            return True

        def blocking_communicate(*args, **kwargs):
            time.sleep(2)
            return ("result", "")

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.Popen") as Popen:
                proc = MagicMock()
                proc.communicate = blocking_communicate
                proc.terminate = MagicMock()
                # First wait() times out, second wait() succeeds
                proc.wait = MagicMock(side_effect=[subprocess.TimeoutExpired("cmd", 5), None])
                proc.kill = MagicMock()
                Popen.return_value = proc

                with pytest.raises(CancellationError):
                    optimize_prompt_with_ollama(
                        "test", config=config, cancel_check=cancel_immediately
                    )

                # Verify terminate, wait (timeout), kill, wait sequence
                proc.terminate.assert_called_once()
                assert proc.wait.call_count == 2
                proc.kill.assert_called_once()
        cache.clear()


@pytest.mark.unit
class TestCancelCheckExceptionHandling:
    """Test exception handling in cancel_check callback."""

    def test_cancel_check_exception_is_warned_but_not_raised(self):
        """User exceptions in cancel_check should be warned but not stop optimization."""
        import time

        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)

        call_count = [0]

        def buggy_cancel_check():
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("Simulated user error in cancel_check")
            return False

        def slow_communicate(*args, **kwargs):
            # Sleep to allow cancel_check to be called multiple times
            time.sleep(0.5)
            return ("optimized", "")

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.Popen") as Popen:
                proc = MagicMock()
                proc.communicate = slow_communicate
                proc.returncode = 0
                Popen.return_value = proc

                # Suppress expected RuntimeWarning from buggy cancel_check (we are testing it is not raised)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=RuntimeWarning)
                    result = optimize_prompt_with_ollama(
                        "test", config=config, cancel_check=buggy_cancel_check
                    )

                # Should have completed successfully
                assert result == "optimized"

                # Verify cancel_check was called at least once (it raised exception but was handled)
                assert call_count[0] >= 1, "cancel_check should be called despite raising exception"
        cache.clear()

    def test_keyboard_interrupt_in_cancel_check_is_reraised(self):
        """KeyboardInterrupt in cancel_check should be re-raised, not swallowed."""
        import time

        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)

        def cancel_with_keyboard_interrupt():
            raise KeyboardInterrupt("User pressed Ctrl+C")

        def blocking_communicate(*args, **kwargs):
            time.sleep(2)
            return ("result", "")

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.subprocess.Popen") as Popen:
                proc = MagicMock()
                proc.communicate = blocking_communicate
                proc.returncode = 0
                Popen.return_value = proc

                # KeyboardInterrupt should be re-raised
                with pytest.raises(KeyboardInterrupt):
                    optimize_prompt_with_ollama(
                        "test", config=config, cancel_check=cancel_with_keyboard_interrupt
                    )
        cache.clear()
