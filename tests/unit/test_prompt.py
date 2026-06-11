"""Unit tests for prompt validation and optimization (mocked)."""

import warnings
from unittest.mock import MagicMock, patch

import pytest

from genimg.core.config import Config
from genimg.core.prompt import (
    OPTIMIZATION_TEMPLATE,
    _assemble_ideogram_json,
    _strip_ollama_thinking,
    check_ollama_available,
    list_ollama_image_models,
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

    def test_strips_ollama_tty_line_edit_sequences(self):
        """Ollama pipes CSI erase/cursor sequences into stdout; strip so UI stays clean."""
        esc = "\x1b"
        raw = (
            f"A warm morning in a bathroom, the walls painted a soft{esc}[4D{esc}[K"
            "soft pale blue."
        )
        assert _strip_ollama_thinking(raw) == (
            "A warm morning in a bathroom, the walls painted a softsoft pale blue."
        )

    def test_empty_or_whitespace_unchanged(self):
        assert _strip_ollama_thinking("") == ""
        assert _strip_ollama_thinking("   ") == "   "


@pytest.mark.unit
class TestCheckOllamaAvailable:
    def test_returns_true_when_api_tags_succeeds(self):
        with patch("genimg.core.prompt.requests.get") as m:
            m.return_value = MagicMock(status_code=200)
            assert check_ollama_available() is True
            m.assert_called_once()
            assert m.call_args[0][0].endswith("/api/tags")

    def test_returns_false_when_api_tags_non_200(self):
        with patch("genimg.core.prompt.requests.get") as m:
            m.return_value = MagicMock(status_code=503)
            assert check_ollama_available() is False

    def test_returns_false_on_request_error(self):
        import requests

        with patch("genimg.core.prompt.requests.get") as m:
            m.side_effect = requests.RequestException()
            assert check_ollama_available() is False

    def test_returns_false_on_timeout(self):
        import requests

        with patch("genimg.core.prompt.requests.get") as m:
            m.side_effect = requests.exceptions.Timeout("read", 5)
            assert check_ollama_available() is False


@pytest.mark.unit
class TestListOllamaModels:
    def test_returns_empty_list_when_ollama_not_available(self):
        with patch("genimg.core.prompt.check_ollama_available", return_value=False):
            assert list_ollama_models() == []

    def test_parses_api_tags_json(self):
        body = {
            "models": [
                {"name": "huihui_ai/qwen3.5-abliterated:4b:latest"},
                {"name": "llama2:latest"},
                {"name": "mistral:7b"},
            ]
        }
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.get") as m:
                resp = MagicMock(status_code=200)
                resp.json.return_value = body
                m.return_value = resp
                models = list_ollama_models()
                assert models == ["huihui_ai/qwen3.5-abliterated:4b", "llama2", "mistral:7b"]

    def test_strips_latest_tag(self):
        body = {
            "models": [
                {"name": "model1:latest"},
                {"name": "model2:v1"},
            ]
        }
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.get") as m:
                resp = MagicMock(status_code=200)
                resp.json.return_value = body
                m.return_value = resp
                models = list_ollama_models()
                assert models == ["model1", "model2:v1"]

    def test_returns_empty_list_on_non_200(self):
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.get") as m:
                m.return_value = MagicMock(status_code=503)
                assert list_ollama_models() == []

    def test_returns_empty_list_when_models_missing(self):
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.get") as m:
                resp = MagicMock(status_code=200)
                resp.json.return_value = {}
                m.return_value = resp
                assert list_ollama_models() == []

    def test_handles_request_error(self):
        import requests

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.get") as m:
                m.side_effect = requests.RequestException()
                assert list_ollama_models() == []

    def test_handles_timeout(self):
        import requests

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.get") as m:
                m.side_effect = requests.exceptions.Timeout("read", 5)
                assert list_ollama_models() == []


@pytest.mark.unit
class TestListOllamaImageModels:
    def test_returns_empty_when_ollama_not_available(self):
        with patch("genimg.core.prompt.check_ollama_available", return_value=False):
            assert list_ollama_image_models() == []

    def test_filters_to_x_and_my_namespaces(self):
        with patch(
            "genimg.core.prompt.list_ollama_models",
            return_value=[
                "x/z-image-turbo",
                "x/flux2-klein",
                "my/custom-model",
                "llama2",
                "huihui_ai/qwen3.5-abliterated:4b",
            ],
        ):
            assert list_ollama_image_models() == [
                "x/z-image-turbo",
                "x/flux2-klein",
                "my/custom-model",
            ]

    def test_returns_empty_when_no_matching_namespace(self):
        with patch(
            "genimg.core.prompt.list_ollama_models",
            return_value=["llama2", "mistral:7b"],
        ):
            assert list_ollama_image_models() == []

    def test_returns_empty_when_no_models_installed(self):
        with patch("genimg.core.prompt.list_ollama_models", return_value=[]):
            assert list_ollama_image_models() == []


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
            with patch("genimg.core.prompt.requests.post") as post:
                resp = MagicMock(status_code=200)
                resp.json.return_value = {"response": "  enhanced prompt  \n"}
                post.return_value = resp
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
            with patch("genimg.core.prompt.requests.post") as post:
                result = optimize_prompt_with_ollama("cached", config=config)
        assert result == "from cache"
        post.assert_not_called()
        cache.clear()

    def test_optimize_prompt_with_ollama_timeout_raises(self):
        import requests

        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                post.side_effect = requests.exceptions.Timeout("read", 10)
                with pytest.raises(RequestTimeoutError):
                    optimize_prompt_with_ollama("long prompt", config=config, timeout=10)
        cache.clear()

    def test_optimize_prompt_with_ollama_nonzero_return_raises(self):
        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                post.return_value = MagicMock(status_code=500, text="error message")
                with pytest.raises(APIError) as exc_info:
                    optimize_prompt_with_ollama("abc", config=config)
        assert "error message" in str(exc_info.value)
        cache.clear()

    def test_optimize_prompt_with_ollama_empty_stdout_raises(self):
        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                resp = MagicMock(status_code=200)
                resp.json.return_value = {"response": "   \n"}
                post.return_value = resp
                with pytest.raises(APIError) as exc_info:
                    optimize_prompt_with_ollama("abc", config=config)
        assert "empty" in str(exc_info.value).lower()
        cache.clear()

    def test_optimize_prompt_with_ollama_connection_error_raises(self):
        import requests

        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                post.side_effect = requests.exceptions.ConnectionError()
                with pytest.raises(APIError) as exc_info:
                    optimize_prompt_with_ollama("abc", config=config)
        assert "connect" in str(exc_info.value).lower()
        cache.clear()

    def test_optimize_prompt_with_ollama_think_flag_false_by_default(self):
        """When config.optimize_thinking is False (default), JSON payload has think=False."""
        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        assert config.optimize_thinking is False
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                resp = MagicMock(status_code=200)
                resp.json.return_value = {"response": "optimized"}
                post.return_value = resp
                optimize_prompt_with_ollama("a red car", config=config)
        payload = post.call_args[1]["json"]
        assert payload["think"] is False
        assert payload["model"] == config.default_optimization_model
        assert payload["stream"] is False
        cache.clear()

    def test_optimize_prompt_with_ollama_think_flag_true_when_optimize_thinking(self):
        """When config.optimize_thinking is True, JSON payload has think=True."""
        cache = get_cache()
        cache.clear()
        config = Config(
            openrouter_api_key="sk-x",
            optimization_enabled=True,
            optimize_thinking=True,
        )
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                resp = MagicMock(status_code=200)
                resp.json.return_value = {"response": "optimized"}
                post.return_value = resp
                optimize_prompt_with_ollama("a red car", config=config)
        payload = post.call_args[1]["json"]
        assert payload["think"] is True
        assert payload["model"] == config.default_optimization_model
        cache.clear()

    def test_optimize_prompt_with_reference_description_uses_description_template(self):
        """When reference_description is set, description-based template is used and cached with description_key."""
        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        ref_hash = "abc123"
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch(
                "genimg.core.prompt.get_optimization_template_with_description",
                return_value="Use this: {reference_description}",
            ) as get_desc_tpl:
                with patch("genimg.core.prompt.get_optimization_template") as get_std_tpl:
                    with patch("genimg.core.prompt.requests.post") as post:
                        resp = MagicMock(status_code=200)
                        resp.json.return_value = {"response": "  improved  \n"}
                        post.return_value = resp
                        result = optimize_prompt(
                            "a cat",
                            config=config,
                            reference_hash=ref_hash,
                            reference_description="fluffy orange tabby",
                            enable_cache=True,
                        )
        assert result == "improved"
        get_desc_tpl.assert_called()
        get_std_tpl.assert_not_called()
        # Cache uses description_key (ref_hash) so same prompt+description hits cache
        assert (
            cache.get(
                "a cat", config.default_optimization_model, ref_hash, description_key=ref_hash
            )
            == "improved"
        )
        sent_prompt = post.call_args[1]["json"]["prompt"]
        assert "fluffy orange tabby" in sent_prompt
        cache.clear()

    def test_optimization_template_contains_placeholder(self):
        assert "{reference_image_instruction}" in OPTIMIZATION_TEMPLATE
        assert (
            "visual scene architect" in OPTIMIZATION_TEMPLATE.lower()
            or "scene" in OPTIMIZATION_TEMPLATE.lower()
        )

    def test_cancel_check_raises_cancellation_error(self):
        """When cancel_check returns True, optimization is cancelled while HTTP is in flight."""
        import time

        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        call_count = [0]

        def cancel_after_two():
            call_count[0] += 1
            return call_count[0] >= 2

        def slow_post(*args, **kwargs):
            time.sleep(2)
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"response": "done"}
            return resp

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post", side_effect=slow_post):
                with pytest.raises(CancellationError) as exc_info:
                    optimize_prompt_with_ollama(
                        "original", config=config, cancel_check=cancel_after_two
                    )
        assert "cancelled" in str(exc_info.value).lower()
        cache.clear()


@pytest.mark.unit
class TestOptimizationHttpTimeout:
    """HTTP optimization maps timeouts to RequestTimeoutError."""

    def test_timeout_raises_request_timeout_error(self):
        import requests

        cache = get_cache()
        cache.clear()
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                post.side_effect = requests.exceptions.ReadTimeout("read timed out")
                with pytest.raises(RequestTimeoutError):
                    optimize_prompt_with_ollama("test", config=config, timeout=10)
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

        def slow_post(*args, **kwargs):
            time.sleep(0.5)
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"response": "optimized"}
            return resp

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post", side_effect=slow_post):
                # Suppress expected RuntimeWarning from buggy cancel_check (we are testing it is not raised)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=RuntimeWarning)
                    result = optimize_prompt_with_ollama(
                        "test", config=config, cancel_check=buggy_cancel_check
                    )

                assert result == "optimized"
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

        def blocking_post(*args, **kwargs):
            time.sleep(2)
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"response": "result"}
            return resp

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post", side_effect=blocking_post):
                with pytest.raises(KeyboardInterrupt):
                    optimize_prompt_with_ollama(
                        "test", config=config, cancel_check=cancel_with_keyboard_interrupt
                    )
        cache.clear()


@pytest.mark.unit
class TestAssembleIdeogramJson:
    """Tests for _assemble_ideogram_json()."""

    def _full_caption(self) -> dict:
        return {
            "high_level_description": "A barista pouring latte art.",
            "style_description": {
                "aesthetics": "warm, cozy",
                "lighting": "soft morning light",
                "photo": "shallow depth of field",
                "medium": "photograph",
            },
            "compositional_deconstruction": {
                "background": "A cozy cafe interior.",
                "elements": [
                    {"type": "obj", "desc": "A barista in a white apron."},
                    {"type": "obj", "desc": "A ceramic mug with latte art."},
                ],
            },
        }

    def test_full_caption_includes_all_sections(self):
        result = _assemble_ideogram_json(self._full_caption())
        assert "A barista pouring latte art." in result
        assert "warm, cozy" in result
        assert "A cozy cafe interior." in result
        assert "A barista in a white apron." in result
        assert "A ceramic mug with latte art." in result

    def test_text_element_formatted_with_prefix(self):
        data = {
            "high_level_description": "A poster.",
            "compositional_deconstruction": {
                "background": "Plain white.",
                "elements": [
                    {"type": "text", "text": "HELLO", "desc": "bold serif at top"},
                ],
            },
        }
        result = _assemble_ideogram_json(data)
        assert 'Text reading "HELLO": bold serif at top' in result

    def test_text_element_no_desc(self):
        data = {
            "compositional_deconstruction": {
                "background": "bg",
                "elements": [{"type": "text", "text": "SIGN"}],
            }
        }
        result = _assemble_ideogram_json(data)
        assert 'Text reading "SIGN"' in result

    def test_art_style_included(self):
        data = {
            "style_description": {
                "aesthetics": "minimal",
                "lighting": "even",
                "art_style": "flat vector illustration",
                "medium": "graphic_design",
            },
            "compositional_deconstruction": {"background": "white", "elements": []},
        }
        result = _assemble_ideogram_json(data)
        assert "flat vector illustration" in result

    def test_missing_top_level_fields_handled_gracefully(self):
        result = _assemble_ideogram_json({})
        assert result == ""

    def test_sections_joined_with_double_newline(self):
        result = _assemble_ideogram_json(self._full_caption())
        assert "\n\n" in result

    def test_empty_elements_list(self):
        data = {
            "high_level_description": "Minimal scene.",
            "compositional_deconstruction": {"background": "Plain.", "elements": []},
        }
        result = _assemble_ideogram_json(data)
        assert "Minimal scene." in result
        assert "Plain." in result


@pytest.mark.unit
class TestJsonOptimizationFormat:
    """Tests for JSON optimization format path in optimize_prompt_with_ollama."""

    def setup_method(self):
        get_cache().clear()

    def teardown_method(self):
        get_cache().clear()

    def _valid_caption_json(self) -> str:
        import json

        return json.dumps(
            {
                "high_level_description": "A golden retriever on a skateboard.",
                "style_description": {
                    "aesthetics": "playful, vibrant",
                    "lighting": "bright afternoon",
                    "photo": "eye-level, shallow depth",
                    "medium": "photograph",
                },
                "compositional_deconstruction": {
                    "background": "A sunny sidewalk.",
                    "elements": [{"type": "obj", "desc": "A golden retriever on a red skateboard."}],
                },
            }
        )

    def test_json_format_adds_format_key_to_payload(self):
        """When optimize_format is 'json', Ollama payload includes format='json'."""
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True, optimize_format="json")
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                resp = MagicMock(status_code=200)
                resp.json.return_value = {"response": self._valid_caption_json()}
                post.return_value = resp
                optimize_prompt_with_ollama("a dog on a skateboard", config=config)
        payload = post.call_args[1]["json"]
        assert payload.get("format") == "json"

    def test_prose_format_omits_format_key_from_payload(self):
        """When optimize_format is 'prose' (default), Ollama payload has no 'format' key."""
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True)
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                resp = MagicMock(status_code=200)
                resp.json.return_value = {"response": "optimized prose"}
                post.return_value = resp
                optimize_prompt_with_ollama("a red car", config=config)
        payload = post.call_args[1]["json"]
        assert "format" not in payload

    def test_json_format_response_assembled_to_prose(self):
        """Valid JSON response is parsed and assembled; returned string is plain prose."""
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True, optimize_format="json")
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                resp = MagicMock(status_code=200)
                resp.json.return_value = {"response": self._valid_caption_json()}
                post.return_value = resp
                result = optimize_prompt_with_ollama("a dog on a skateboard", config=config)
        assert "golden retriever" in result
        assert "sunny sidewalk" in result
        # Result must be plain text, not raw JSON
        assert result.strip()[0] != "{"

    def test_json_format_invalid_json_falls_back_to_raw_text(self):
        """When JSON parse fails, raw Ollama text is returned (no exception raised)."""
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True, optimize_format="json")
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                resp = MagicMock(status_code=200)
                resp.json.return_value = {"response": "not valid json output"}
                post.return_value = resp
                result = optimize_prompt_with_ollama("a cat", config=config)
        assert result == "not valid json output"

    def test_json_format_uses_json_template(self):
        """optimize_format='json' uses the JSON template, not the prose template."""
        config = Config(openrouter_api_key="sk-x", optimization_enabled=True, optimize_format="json")
        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.get_optimization_template_json") as mock_json_tpl:
                mock_json_tpl.return_value = "json tpl {reference_image_instruction}"
                with patch("genimg.core.prompt.get_optimization_template") as mock_prose_tpl:
                    with patch("genimg.core.prompt.requests.post") as post:
                        resp = MagicMock(status_code=200)
                        resp.json.return_value = {"response": self._valid_caption_json()}
                        post.return_value = resp
                        optimize_prompt_with_ollama("a red car", config=config)
            mock_json_tpl.assert_called()
            mock_prose_tpl.assert_not_called()

    def test_json_format_cache_key_is_separate_from_prose(self):
        """prose and json format produce distinct cache entries for the same input."""
        cache = get_cache()

        config_prose = Config(
            openrouter_api_key="sk-x", optimization_enabled=True, optimize_format="prose"
        )
        config_json = Config(
            openrouter_api_key="sk-x", optimization_enabled=True, optimize_format="json"
        )
        model = config_prose.default_optimization_model

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                resp_prose = MagicMock(status_code=200)
                resp_prose.json.return_value = {"response": "prose result"}
                post.return_value = resp_prose
                optimize_prompt_with_ollama("a red car", config=config_prose)

        with patch("genimg.core.prompt.check_ollama_available", return_value=True):
            with patch("genimg.core.prompt.requests.post") as post:
                resp_json = MagicMock(status_code=200)
                resp_json.json.return_value = {"response": self._valid_caption_json()}
                post.return_value = resp_json
                optimize_prompt_with_ollama("a red car", config=config_json)

        prose_cached = cache.get("a red car", model, optimize_format="prose")
        json_cached = cache.get("a red car", model, optimize_format="json")
        assert prose_cached is not None
        assert json_cached is not None
        assert prose_cached != json_cached
