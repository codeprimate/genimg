"""Unit tests for Wiro schema parsing and run plan construction."""

import base64
import io

import pytest
from PIL import Image

from genimg.core.providers.wiro_schema import (
    ContentMode,
    aspect_choices_from_schema,
    build_run_plan,
    model_has_file_inputs,
    parse_model_slugs,
    resolution_frames,
)
from genimg.utils.exceptions import ValidationError

_MINIMAL_PNG_BUF = io.BytesIO()
Image.new("RGB", (1, 1), color=(0, 0, 0)).save(_MINIMAL_PNG_BUF, format="PNG")
MINIMAL_PNG = _MINIMAL_PNG_BUF.getvalue()

SCHEMA_TXT2IMG = {
    "tool": [
        {
            "parameters": [
                {
                    "items": [
                        {"id": "prompt", "type": "textarea", "required": True},
                    ]
                }
            ]
        }
    ]
}

SCHEMA_TXT2IMG_WITH_ASPECT = {
    "tool": [
        {
            "parameters": [
                {
                    "items": [
                        {"id": "prompt", "type": "textarea", "required": True},
                        {
                            "id": "aspectRatio",
                            "type": "select",
                            "required": False,
                            "default": "16:9",
                            "options": [
                                {"value": "", "text": "auto"},
                                {"value": "1:1", "text": "1:1"},
                                {"value": "16:9", "text": "16:9"},
                            ],
                        },
                    ]
                }
            ]
        }
    ]
}

SCHEMA_WITH_FILE = {
    "tool": [
        {
            "parameters": [
                {
                    "items": [
                        {"id": "prompt", "type": "textarea", "required": True},
                        {"id": "inputImage", "type": "fileinput", "required": True},
                    ]
                }
            ]
        }
    ]
}

SCHEMA_WITH_REQUIRED_EXTRAS = {
    "tool": [
        {
            "parameters": [
                {
                    "items": [
                        {"id": "prompt", "type": "textarea", "required": True},
                        {
                            "id": "maxImages",
                            "type": "number",
                            "required": True,
                        },
                        {
                            "id": "watermark",
                            "type": "select",
                            "required": True,
                            "options": [
                                {"value": "false", "text": "false"},
                                {"value": "true", "text": "true"},
                            ],
                        },
                    ]
                }
            ]
        }
    ]
}

SCHEMA_WITH_FILE_AND_ASPECT = {
    "tool": [
        {
            "parameters": [
                {
                    "items": [
                        {"id": "prompt", "type": "textarea", "required": True},
                        {"id": "inputImage", "type": "fileinput", "required": True},
                        {
                            "id": "aspectRatio",
                            "type": "select",
                            "required": False,
                            "options": [
                                {"value": "", "text": "auto"},
                                {"value": "1:1", "text": "1:1"},
                                {"value": "16:9", "text": "16:9"},
                            ],
                        },
                    ]
                }
            ]
        }
    ]
}

SCHEMA_WITH_FILE_AND_DIMENSIONS = {
    "tool": [
        {
            "parameters": [
                {
                    "items": [
                        {"id": "prompt", "type": "textarea", "required": True},
                        {"id": "inputImage", "type": "combinefileinput", "required": False},
                        {"id": "width", "type": "number", "required": False},
                        {"id": "height", "type": "number", "required": False},
                    ]
                }
            ]
        }
    ]
}


@pytest.mark.unit
class TestParseModelSlugs:
    def test_valid_model(self):
        assert parse_model_slugs("bytedance/seedream-v4-5-uncensored") == (
            "bytedance",
            "seedream-v4-5-uncensored",
        )

    def test_invalid_model_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            parse_model_slugs("noseparator")
        assert exc_info.value.field == "model"


@pytest.mark.unit
class TestModelHasFileInputs:
    def test_txt2img_false(self):
        assert model_has_file_inputs(SCHEMA_TXT2IMG) is False

    def test_with_fileinput_true(self):
        assert model_has_file_inputs(SCHEMA_WITH_FILE) is True


@pytest.mark.unit
class TestBuildRunPlan:
    def test_json_plan_without_refs(self):
        plan = build_run_plan(SCHEMA_TXT2IMG, prompt="hello", reference_images_b64=None)
        assert plan.content_mode == ContentMode.JSON
        assert plan.json_fields == {"prompt": "hello"}
        assert plan.multipart_files == ()

    def test_json_plan_t2i_omits_aspect_without_defaultvalue(self):
        plan = build_run_plan(
            SCHEMA_TXT2IMG_WITH_ASPECT,
            prompt="hello",
            reference_images_b64=None,
        )
        assert plan.content_mode == ContentMode.JSON
        assert "aspectRatio" not in plan.json_fields

    def test_json_plan_includes_required_schema_fields(self):
        plan = build_run_plan(
            SCHEMA_WITH_REQUIRED_EXTRAS,
            prompt="hello",
            reference_images_b64=None,
        )
        assert plan.json_fields == {
            "maxImages": "1",
            "watermark": "false",
            "prompt": "hello",
        }

    def test_multipart_plan_with_ref(self):
        ref_b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
        plan = build_run_plan(
            SCHEMA_WITH_FILE,
            prompt="edit",
            reference_images_b64=[ref_b64],
        )
        assert plan.content_mode == ContentMode.MULTIPART
        assert plan.multipart_text_fields["prompt"] == "edit"
        assert plan.multipart_text_fields["inputImageUrl"] == ""
        assert len(plan.multipart_files) == 1
        field_name, filename, content, content_type = plan.multipart_files[0]
        assert field_name == "inputImage"
        assert filename == "inputImage.png"
        assert content == MINIMAL_PNG
        assert content_type == "image/png"

    def test_multipart_plan_with_ref_omits_aspect_without_defaultvalue(self):
        ref_b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
        plan = build_run_plan(
            SCHEMA_WITH_FILE_AND_ASPECT,
            prompt="edit",
            reference_images_b64=[ref_b64],
        )
        assert "aspectRatio" not in plan.multipart_text_fields

    def test_json_plan_without_ref_omits_aspect_without_defaultvalue(self):
        plan = build_run_plan(
            SCHEMA_WITH_FILE_AND_ASPECT,
            prompt="edit",
            reference_images_b64=None,
        )
        assert "aspectRatio" not in plan.json_fields

    def test_multipart_plan_with_ref_omits_width_height_without_defaultvalue(self):
        ref_b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
        plan = build_run_plan(
            SCHEMA_WITH_FILE_AND_DIMENSIONS,
            prompt="edit",
            reference_images_b64=[ref_b64],
        )
        assert "width" not in plan.multipart_text_fields
        assert "height" not in plan.multipart_text_fields

    def test_json_plan_without_ref_does_not_set_width_height(self):
        plan = build_run_plan(
            SCHEMA_WITH_FILE_AND_DIMENSIONS,
            prompt="edit",
            reference_images_b64=None,
        )
        assert "width" not in plan.json_fields
        assert "height" not in plan.json_fields

    def test_refs_without_file_inputs_raises(self):
        ref_b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
        with pytest.raises(ValidationError) as exc_info:
            build_run_plan(
                SCHEMA_TXT2IMG,
                prompt="x",
                reference_images_b64=[ref_b64],
                model_label="test/model",
            )
        assert exc_info.value.field == "reference_image"


def _tool_schema(items: list[dict[str, object]]) -> dict[str, object]:
    return {"tool": [{"parameters": [{"items": items}]}]}


def _ref_b64() -> str:
    return base64.b64encode(MINIMAL_PNG).decode("ascii")


def _plan_fields(plan: object) -> dict[str, str]:
    content_mode = plan.content_mode  # type: ignore[attr-defined]
    if content_mode == ContentMode.JSON:
        return plan.json_fields  # type: ignore[attr-defined]
    return plan.multipart_text_fields  # type: ignore[attr-defined]


def _prompt_item() -> dict[str, object]:
    return {"id": "prompt", "type": "textarea", "required": True}


def _file_item() -> dict[str, object]:
    return {"id": "inputImage", "type": "fileinput", "required": False}


def _pixel_item(field_id: str, **extra: object) -> dict[str, object]:
    item: dict[str, object] = {"id": field_id, "type": "number", "required": False}
    item.update(extra)
    return item


@pytest.mark.unit
class TestResolutionFrames:
    def test_colon_and_parenthesis_forms(self) -> None:
        assert resolution_frames("2k: 2560x1440, 4k: 3840×2160") == [
            ("2k", 2560),
            ("4k", 3840),
        ]
        assert resolution_frames("(1K)1376x768") == [("1K", 1376)]

    def test_text_without_a_tier_is_empty(self) -> None:
        assert resolution_frames("16:9") == []


@pytest.mark.unit
class TestOmittedSizeDefaults:
    def test_copies_nonempty_aspect_defaultvalue(self) -> None:
        schema = _tool_schema(
            [
                _prompt_item(),
                {
                    "id": "aspectRatio",
                    "type": "select",
                    "defaultvalue": "1:1",
                    "options": [{"value": "1:1", "text": "1:1"}],
                },
            ]
        )
        plan = build_run_plan(schema, prompt="hello", reference_images_b64=None)
        assert plan.json_fields["aspectRatio"] == "1:1"

    def test_blank_and_missing_defaultvalue_are_omitted(self) -> None:
        blank = _tool_schema(
            [
                _prompt_item(),
                {
                    "id": "aspectRatio",
                    "type": "select",
                    "defaultvalue": "  ",
                    "options": [{"value": "16:9", "text": "16:9"}],
                },
            ]
        )
        missing = _tool_schema(
            [
                _prompt_item(),
                {
                    "id": "aspectRatio",
                    "type": "select",
                    "options": [{"value": "16:9", "text": "16:9"}],
                },
            ]
        )
        assert (
            "aspectRatio"
            not in build_run_plan(blank, prompt="hello", reference_images_b64=None).json_fields
        )
        assert (
            "aspectRatio"
            not in build_run_plan(missing, prompt="hello", reference_images_b64=None).json_fields
        )

    def test_pixel_defaultvalue_respects_positive_bounds(self) -> None:
        copied = _tool_schema(
            [
                _prompt_item(),
                _pixel_item("width", defaultvalue="1024", minvalue=0, maxvalue=2048),
                _pixel_item("height", defaultvalue="1024", minvalue=0, maxvalue=2048),
            ]
        )
        omitted = _tool_schema(
            [
                _prompt_item(),
                _pixel_item("width", default="1024", defaultvalue="4096", maxvalue=2048),
                _pixel_item("height", default="1024", defaultvalue="4096", maxvalue=2048),
            ]
        )
        copied_fields = build_run_plan(
            copied, prompt="hello", reference_images_b64=None
        ).json_fields
        assert copied_fields["width"] == "1024"
        assert copied_fields["height"] == "1024"
        omitted_fields = build_run_plan(
            omitted, prompt="hello", reference_images_b64=None
        ).json_fields
        assert "width" not in omitted_fields
        assert "height" not in omitted_fields

    def test_required_blank_size_field_is_omitted_and_max_images_stays(self) -> None:
        schema = _tool_schema(
            [
                _prompt_item(),
                {"id": "maxImages", "type": "number", "required": True},
                {
                    "id": "aspectRatio",
                    "type": "select",
                    "required": True,
                    "defaultvalue": "",
                    "options": [{"value": "1:1", "text": "1:1"}],
                },
            ]
        )
        fields = build_run_plan(schema, prompt="hello", reference_images_b64=None).json_fields
        assert fields["maxImages"] == "1"
        assert "aspectRatio" not in fields

    def test_prompt_only_schema_with_a_pair_adds_no_size_keys(self) -> None:
        plan = build_run_plan(
            SCHEMA_TXT2IMG,
            prompt="hello",
            reference_images_b64=None,
            aspect_ratio="16:9",
            max_extent=1024,
        )
        assert plan.json_fields == {"prompt": "hello"}


@pytest.mark.unit
class TestPixelSizeMapping:
    def _schema(
        self, *, minvalue: int, maxvalue: int, with_file: bool = False
    ) -> dict[str, object]:
        items: list[dict[str, object]] = [_prompt_item()]
        if with_file:
            items.append(_file_item())
        items.append(
            _pixel_item("width", minvalue=minvalue, maxvalue=maxvalue, defaultvalue="1024")
        )
        items.append(
            _pixel_item("height", minvalue=minvalue, maxvalue=maxvalue, defaultvalue="1024")
        )
        return _tool_schema(items)

    def test_square_at_2048(self) -> None:
        fields = _plan_fields(
            build_run_plan(
                self._schema(minvalue=0, maxvalue=2048),
                prompt="hello",
                reference_images_b64=None,
                aspect_ratio="1:1",
                max_extent=2048,
            )
        )
        assert fields["width"] == "2048"
        assert fields["height"] == "2048"
        assert "aspectRatio" not in fields
        assert "resolution" not in fields

    def test_sixteen_nine_short_side_can_be_below_1024(self) -> None:
        fields = _plan_fields(
            build_run_plan(
                self._schema(minvalue=0, maxvalue=2048),
                prompt="hello",
                reference_images_b64=None,
                aspect_ratio="16:9",
                max_extent=1024,
            )
        )
        assert fields["width"] == "1024"
        assert fields["height"] == "576"

    def test_auto_is_square(self) -> None:
        fields = _plan_fields(
            build_run_plan(
                self._schema(minvalue=0, maxvalue=2048),
                prompt="hello",
                reference_images_b64=None,
                aspect_ratio="auto",
                max_extent=1024,
            )
        )
        assert fields["width"] == "1024"
        assert fields["height"] == "1024"

    def test_schema_max_scales_the_pair(self) -> None:
        fields = _plan_fields(
            build_run_plan(
                self._schema(minvalue=0, maxvalue=1536),
                prompt="hello",
                reference_images_b64=None,
                aspect_ratio="1:1",
                max_extent=2048,
            )
        )
        assert fields["width"] == "1536"
        assert fields["height"] == "1536"

    def test_impossible_floor_and_ceiling_uses_fallback(self) -> None:
        fields = _plan_fields(
            build_run_plan(
                self._schema(minvalue=1024, maxvalue=1280),
                prompt="hello",
                reference_images_b64=None,
                aspect_ratio="16:9",
                max_extent=2048,
            )
        )
        assert fields["width"] == "1280"
        assert fields["height"] == "1024"

    def test_json_and_multipart_use_the_same_pixel_strings(self) -> None:
        kwargs = {
            "prompt": "hello",
            "aspect_ratio": "16:9",
            "max_extent": 1024,
        }
        json_fields = _plan_fields(
            build_run_plan(
                self._schema(minvalue=0, maxvalue=2048),
                reference_images_b64=None,
                **kwargs,
            )
        )
        multipart_fields = _plan_fields(
            build_run_plan(
                self._schema(minvalue=0, maxvalue=2048, with_file=True),
                reference_images_b64=[_ref_b64()],
                **kwargs,
            )
        )
        assert json_fields["width"] == multipart_fields["width"] == "1024"
        assert json_fields["height"] == multipart_fields["height"] == "576"


def _ratio_schema(
    aspect_options: list[dict[str, str]],
    resolution_options: list[dict[str, str]] | None = None,
    *,
    defaultvalue: str | None = None,
    with_pixels: bool = False,
) -> dict[str, object]:
    aspect: dict[str, object] = {
        "id": "aspectRatio",
        "type": "select",
        "options": aspect_options,
    }
    if defaultvalue is not None:
        aspect["defaultvalue"] = defaultvalue
    items: list[dict[str, object]] = [_prompt_item(), aspect]
    if resolution_options is not None:
        items.append({"id": "resolution", "type": "select", "options": resolution_options})
    if with_pixels:
        items.append(_pixel_item("width"))
        items.append(_pixel_item("height"))
    return _tool_schema(items)


def _ratio_fields(schema: dict[str, object], aspect_ratio: str, max_extent: int) -> dict[str, str]:
    return _plan_fields(
        build_run_plan(
            schema,
            prompt="hello",
            reference_images_b64=None,
            aspect_ratio=aspect_ratio,
            max_extent=max_extent,
        )
    )


@pytest.mark.unit
class TestRatioSizeMapping:
    def test_exact_value_keeps_schema_spelling(self) -> None:
        fields = _ratio_fields(
            _ratio_schema(
                [
                    {"value": "1:1", "text": "1:1"},
                    {"value": "16:9", "text": "16:9"},
                ]
            ),
            "16:9",
            1024,
        )
        assert fields["aspectRatio"] == "16:9"
        assert "width" not in fields
        assert "height" not in fields

    def test_case_difference_sends_schema_spelling(self) -> None:
        fields = _ratio_fields(
            _ratio_schema([{"value": "Auto", "text": "Auto"}]),
            "auto",
            1024,
        )
        assert fields["aspectRatio"] == "Auto"

    def test_seven_five_snaps_to_closer_sixteen_nine(self) -> None:
        # |7/5 - 16/9| is smaller than |7/5 - 1|.
        fields = _ratio_fields(
            _ratio_schema(
                [
                    {"value": "1:1", "text": "1:1"},
                    {"value": "16:9", "text": "16:9"},
                ]
            ),
            "7:5",
            1024,
        )
        assert fields["aspectRatio"] == "16:9"

    def test_equal_distance_keeps_the_earlier_option(self) -> None:
        fields = _ratio_fields(
            _ratio_schema(
                [
                    {"value": "1:2", "text": "1:2"},
                    {"value": "2:1", "text": "2:1"},
                ]
            ),
            "1:1",
            1024,
        )
        assert fields["aspectRatio"] == "1:2"

    def test_auto_blank_value_is_sent(self) -> None:
        fields = _ratio_fields(
            _ratio_schema([{"value": "", "text": "auto"}, {"value": "1:1", "text": "1:1"}]),
            "auto",
            1024,
        )
        assert fields["aspectRatio"] == ""

    def test_auto_match_input_image(self) -> None:
        fields = _ratio_fields(
            _ratio_schema([{"value": "follow", "text": "Match Input Image"}]),
            "auto",
            1024,
        )
        assert fields["aspectRatio"] == "follow"

    def test_auto_without_auto_option_uses_defaultvalue(self) -> None:
        fields = _ratio_fields(
            _ratio_schema(
                [{"value": "1:1", "text": "1:1"}, {"value": "16:9", "text": "16:9"}],
                defaultvalue="9:16",
            ),
            "auto",
            1024,
        )
        assert fields["aspectRatio"] == "9:16"

    def test_auto_without_auto_option_uses_first_value(self) -> None:
        fields = _ratio_fields(
            _ratio_schema([{"value": "16:9", "text": "16:9"}, {"value": "1:1", "text": "1:1"}]),
            "auto",
            1024,
        )
        assert fields["aspectRatio"] == "16:9"

    def test_frame_text_picks_the_closer_tier(self) -> None:
        schema = _ratio_schema(
            [
                {"value": "1:1", "text": "1:1"},
                {"value": "16:9", "text": "2k: 2560x1440, 4k: 3840x2160"},
            ],
            [{"value": "2k", "text": "2K"}, {"value": "4k", "text": "4K"}],
        )
        fields = _ratio_fields(schema, "16:9", 2048)
        assert fields["aspectRatio"] == "16:9"
        assert fields["resolution"] == "2k"

    def test_closer_frame_that_does_not_need_a_tie_break(self) -> None:
        schema = _ratio_schema(
            [{"value": "1:1", "text": "1k: 1920x1920, 3k: 2880x2880"}],
            [{"value": "1k", "text": "1k"}, {"value": "3k", "text": "3k"}],
        )
        assert _ratio_fields(schema, "1:1", 2048)["resolution"] == "1k"

    def test_equal_frame_distance_prefers_the_side_within_extent(self) -> None:
        schema = _ratio_schema(
            [{"value": "1:1", "text": "1k: 1024x1024, 3k: 3072x3072"}],
            [{"value": "1k", "text": "1k"}, {"value": "3k", "text": "3k"}],
        )
        assert _ratio_fields(schema, "1:1", 2048)["resolution"] == "1k"

    def test_nominal_k_when_the_aspect_text_has_no_frames(self) -> None:
        schema = _ratio_schema(
            [{"value": "16:9", "text": "16:9"}],
            [{"value": "2k", "text": "2k"}, {"value": "4k", "text": "4k"}],
        )
        assert _ratio_fields(schema, "16:9", 2048)["resolution"] == "2k"

    def test_unreadable_resolution_is_omitted(self) -> None:
        schema = _ratio_schema(
            [{"value": "16:9", "text": "16:9"}],
            [{"value": "high", "text": "high"}, {"value": "low", "text": "low"}],
        )
        assert "resolution" not in _ratio_fields(schema, "16:9", 2048)

    def test_ratio_model_does_not_send_pixel_fields(self) -> None:
        schema = _ratio_schema(
            [{"value": "16:9", "text": "16:9"}],
            with_pixels=True,
        )
        fields = _ratio_fields(schema, "16:9", 1024)
        assert fields["aspectRatio"] == "16:9"
        assert "width" not in fields
        assert "height" not in fields


@pytest.mark.unit
class TestAspectChoicesFromSchema:
    def test_select_uses_option_text_as_the_label(self) -> None:
        schema = _ratio_schema([{"value": "16:9", "text": "Landscape 16:9"}])
        assert aspect_choices_from_schema(schema) == [("Landscape 16:9", "16:9")]

    def test_pixel_schema_returns_none(self) -> None:
        schema = _tool_schema(
            [
                _prompt_item(),
                _pixel_item("width"),
                _pixel_item("height"),
            ]
        )
        assert aspect_choices_from_schema(schema) is None

    def test_blank_auto_value_submits_auto(self) -> None:
        schema = _ratio_schema([{"value": "", "text": "auto"}])
        assert aspect_choices_from_schema(schema) == [("auto", "auto")]
