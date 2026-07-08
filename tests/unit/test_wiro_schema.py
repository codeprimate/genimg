"""Unit tests for Wiro schema parsing and run plan construction."""

import base64
import io

import pytest
from PIL import Image

from genimg.core.providers.wiro_schema import (
    ContentMode,
    build_run_plan,
    model_has_file_inputs,
    parse_model_slugs,
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

    def test_multipart_plan_with_ref_sets_square_aspect_ratio(self):
        ref_b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
        plan = build_run_plan(
            SCHEMA_WITH_FILE_AND_ASPECT,
            prompt="edit",
            reference_images_b64=[ref_b64],
        )
        assert plan.multipart_text_fields["aspectRatio"] == "1:1"

    def test_multipart_plan_without_ref_leaves_aspect_ratio_unset(self):
        plan = build_run_plan(
            SCHEMA_WITH_FILE_AND_ASPECT,
            prompt="edit",
            reference_images_b64=None,
        )
        assert "aspectRatio" not in plan.json_fields

    def test_multipart_plan_with_ref_sets_square_width_height(self):
        ref_b64 = base64.b64encode(MINIMAL_PNG).decode("ascii")
        plan = build_run_plan(
            SCHEMA_WITH_FILE_AND_DIMENSIONS,
            prompt="edit",
            reference_images_b64=[ref_b64],
        )
        assert plan.multipart_text_fields["width"] == "1024"
        assert plan.multipart_text_fields["height"] == "1024"

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
