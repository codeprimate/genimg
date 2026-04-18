"""Unit tests for Variation C progress helpers."""

from pathlib import Path
from unittest.mock import patch

import pytest

from genimg.cli import progress


@pytest.mark.unit
def test_print_character_banner_calls_console() -> None:
    with patch.object(progress.console, "print") as m_print:
        progress.print_character_banner(
            title="Test │Name",
            ref_count=2,
            provider_id="openrouter",
            model_id="bytedance-seed/seedream-4.5",
        )
    assert m_print.call_count == 3
    joined = " ".join(str(c.args[0]) for c in m_print.call_args_list)
    assert "genimg character" in joined
    assert "refs=2" in joined
    assert "seedream-4.5" in joined


@pytest.mark.unit
def test_print_character_post_summary_truncates_many_refs() -> None:
    with patch.object(progress.console, "print") as m_print:
        progress.print_character_post_summary(
            ref_paths=[
                Path("/a/one.png"),
                Path("/b/two.png"),
                Path("/c/three.png"),
                Path("/d/four.png"),
            ],
            user_prompt=None,
            generation_time=1.25,
            out_path=Path("/tmp/out.png"),
            verbose_level=0,
        )
    lines = [c.args[0] for c in m_print.call_args_list]
    assert any("+1 more" in ln for ln in lines)


@pytest.mark.unit
def test_print_character_post_summary_verbose_uses_full_paths() -> None:
    with patch.object(progress.console, "print") as m_print:
        progress.print_character_post_summary(
            ref_paths=[Path("/x/a.png")],
            user_prompt="hi",
            generation_time=2.0,
            out_path=Path("out.png"),
            verbose_level=1,
        )
    lines = [c.args[0] for c in m_print.call_args_list]
    assert any("/x/a.png" in ln for ln in lines)
