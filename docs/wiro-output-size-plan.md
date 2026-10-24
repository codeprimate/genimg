# Implementation TODO: Output size on the CLI, library, and web UI

## Specification Reference
**Source Document**: [docs/wiro-output-size-specification.md](wiro-output-size-specification.md)
*This specification document must be loaded alongside this plan during execution to provide complete context and requirements.*

## Overview
- **Complexity**: Moderate
- **Risk Level**: Medium
- **Key Dependencies**: Wiro Tool/Detail schema (`defaultvalue`, `aspectRatio`, `resolution`, `width`, `height`), `generate_image()`, Draw Things `round_dimension_to_multiple_of_64`, the process-wide Wiro schema cache in `src/genimg/core/providers/wiro.py`
- **Estimated Effort**: About one focused day
- **Specification Sections**: Problem Statement, Functional Requirements, Wiro pixel models, Wiro ratio models, Draw Things, OpenRouter and Ollama, Bitmap fit, Omitted request, Technical Constraints, Edge Cases & Error Handling, Technical Approach, Acceptance Criteria, Out of Scope

## Phase Strategy
The caller-facing pair is one contract. Phase 1 puts that contract and the bitmap fit in one module and teaches every `generate()` method to accept the pair. Later phases only map the pair. Wiro schema mapping, Draw Things canvas snap, the CLI, and Gradio can each be tested on their own. Docs land last so the changelog describes the finished behavior.

Each phase ends with `.venv/bin/ruff check src/ tests/`, `.venv/bin/mypy src/`, and `.venv/bin/pytest tests/unit/`.

## Locked Decisions
These choices are fixed for execution. They close gaps where the spec allows two readings.

1. **One size module.** Add `src/genimg/core/output_size.py`. It holds the named bounds, the fixed aspect list, pair validation, ideal pixel math, and the bitmap fit. Wiro pixel mapping and Draw Things both call `ideal_pixel_size`. Only `generate_image()` calls the fit. A second copy of the pixel formula will drift.
2. **Run fields stay strings.** `ModelRunPlan.json_fields` and `multipart_text_fields` stay `dict[str, str]`. Pixel sizes are decimal strings such as `"2048"`. Multipart bodies are strings. JSON already sends `maxImages` as `"1"`. Do not change the plan type to `int`.
3. **Blank schema values are not the Gradio submit value.** A blank string is an omitted size part. When a Wiro option `value` is blank and its `text` is `auto` or `Match Input Image` (ignore case), the dropdown value is the token `auto`. The ratio adapter still writes that option's real `value`, including `""`.
4. **`auto` is case-insensitive.** Validation normalizes it to `auto` before a provider runs.
5. **Half-pixel ties round away from zero.** Do not use Python `round` (banker's rounding).
6. **The four size ids skip `_static_schema_fields`.** That helper still reads `default` for every other parameter. Only the size mapper reads `defaultvalue`, and only for `aspectRatio`, `resolution`, `width`, and `height`. On the omitted path, do not invent a value when `defaultvalue` is missing or blank, even if `required` is true.
7. **A set pair replaces Draw Things width and height for that run.** Preset size and `GENIMG_DRAW_THINGS_WIDTH_PX` / `GENIMG_DRAW_THINGS_HEIGHT_PX` apply only when the pair is omitted. Do not write the override back onto `Config` or `self._width_px`.
8. **Gradio Output size is its own row.** Place it under the provider and model row and above the LoRA block. Do not put it inside the model column. The model column is half the page and already holds the LoRA stack. Move the LoRA container below the size row. Leave the LoRA widgets as they are. Move the reference warning out of the model column so it spans the full width under the size row.

## Progress Indicators
- 📋 **Planned** - Not started
- 🔄 **In Progress** - Currently being worked on
- ✅ **Completed** - Successfully finished
- ❌ **Blocked/Failed** - Encountered issues or dependencies
- ⏸️ **Paused** - Temporarily suspended
- 🔍 **Under Review** - Completed but needs validation

*Progress indicators should be placed at the end of phase, task, and subtask headings with format: "- ✅ Done"*

## Implementation Phases

## Phase 1: Size contract and bitmap fit - ✅ Done
*Incremental Goal: A caller can pass a legal pair into `generate_image()`. Illegal pairs raise `ValidationError` before a provider runs. The returned bitmap matches the pair. Providers accept the pair and do not change their payloads yet.*

### Task 1.1: Add the size module - ✅ Done
*Spec Reference: Functional Requirements, Bitmap fit, Technical Constraints*

- [x] 1.1.1 **Add named constants and pure helpers** - ✅ Done
  - *Hint*: Follow the constant style in `src/genimg/core/providers/draw_things/constants.py`. Validation errors use `genimg.utils.exceptions.ValidationError` with a `field` argument, as in `generate_image()`.
  - *Consider*: Bounds are code constants. They are not environment variables and they are not `Config` fields.
  - *Files*: `src/genimg/core/output_size.py`
  - *Risk*: Python `round` ties to even. `16:9` at 1024 is exact (576), so a tie test must use a `.5` case on purpose.
  - **IMPLEMENTATION PLAN**:
    - **Constants**:
      - `MIN_OUTPUT_EXTENT = 1024`
      - `MAX_OUTPUT_EXTENT = 2048`
      - `NOMINAL_K_PIXELS = 1024` (used later by the Wiro `<number>k` rule)
      - `AUTO_ASPECT_TOKEN = "auto"`
      - `MATCH_INPUT_IMAGE_TEXT = "Match Input Image"`
      - `MODEL_DEFAULT_LABEL = "Model default"`
      - `FIXED_ASPECT_RATIOS = ("1:1", "5:4", "4:5", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "auto")`
      - `WIRO_SIZE_FIELD_IDS = ("aspectRatio", "resolution", "width", "height")`
    - **Rounding**:
      - `round_half_away_from_zero(value: float) -> int` uses `math.floor(value + 0.5)` for positive values.
    - **Parsing**:
      - `parse_aspect_ratio(token: str) -> tuple[int, int] | None`
      - Return `None` for `auto` (ignore case).
      - Return `(width, height)` when the token is `^\d+:\d+$` and both numbers are greater than 0.
      - Any other token is invalid.
    - **Ideal pixels**:
      - `ideal_pixel_size(aspect_ratio: str, max_extent: int) -> tuple[int, int]`
      - `auto` uses ratio `1:1`.
      - The longer ratio side becomes `max_extent`.
      - The shorter side is `round_half_away_from_zero(max_extent * minor / major)`.
      - `16:9` at 1024 returns `(1024, 576)`. `9:16` at 1024 returns `(576, 1024)`. `1:1` at 2048 returns `(2048, 2048)`.
    - **Pair check**:
      - `normalize_size_pair(aspect_ratio: str | None, max_extent: int | float | str | None) -> tuple[str, int] | None`
      - A blank string and `None` are omitted. A whole-number float such as `1024.0` becomes `int`.
      - Both omitted returns `None`.
      - One omitted and one set raises `ValidationError` before any provider work. Use `field="aspect_ratio"` or `field="max_extent"`.
      - `max_extent` outside 1024 through 2048 raises `ValidationError` with `field="max_extent"`.
      - A token other than `auto` or `W:H` of two positive integers raises `ValidationError` with `field="aspect_ratio"`. `wide` fails. `7:5` succeeds. `0:1` fails.
      - A legal pair returns `(normalized_token, extent)` with `auto` forced to lowercase.
    - **Testing Strategy**:
      - **Code Quality**: `.venv/bin/ruff check src/ tests/` and `.venv/bin/mypy src/`
      - **Unit Testing**: `tests/unit/test_output_size.py`
      - **Integration Testing**: None in this task. No network.
      - **Test Cases**:
        - Blank and `None` pairs normalize to `None`.
        - Aspect without extent, and extent without aspect, raise `ValidationError` and set `field`.
        - Extents 1023 and 2049 raise. Extents 1024 and 2048 do not.
        - `wide`, `16 : 9`, and `0:1` raise. `7:5` and `AUTO` do not. `AUTO` normalizes to `auto`.
        - `ideal_pixel_size("16:9", 1024) == (1024, 576)`
        - `ideal_pixel_size("1:1", 2048) == (2048, 2048)`
        - `ideal_pixel_size("auto", 2048) == (2048, 2048)`
        - A `.5` tie rounds away from zero (for example `1.5` becomes `2`).
      - **Mocks/Fixtures**: None.
      - **Coverage**: Both error fields, both bounds, auto, and a non-schema ratio.

- [x] 1.1.2 **Fit the bitmap in one function** - ✅ Done
  - *Hint*: `GenerationResult.image` is a PIL `Image`. Resize with `Image.Resampling.LANCZOS`. Existing code opens images with `Image.open(...).copy()`.
  - *Consider*: The fit does not read a schema. It does not run for an omitted pair. Providers must not crop or scale.
  - *Files*: `src/genimg/core/output_size.py`
  - *Risk*: Center-crop rounding can leave the long side one pixel off the extent. Resize to the target size computed below so the saved size matches the spec examples.
  - **IMPLEMENTATION PLAN**:
    - **Function**: `fit_image(image: Image.Image, aspect_ratio: str, max_extent: int) -> Image.Image`
    - **`auto`**: Do not crop. Scale so the longer side equals `max_extent`. The shorter side is `round_half_away_from_zero(short * max_extent / long)`. If the long side is already `max_extent`, return a copy.
    - **Any other ratio**:
      - Center-crop to the requested width/height quotient.
      - Crop the axis that is too long. The crop window uses integer pixel edges and stays centered (`(size - crop) // 2`).
      - Then resize to `ideal_pixel_size(aspect_ratio, max_extent)` with Lanczos.
    - **Mode**: Keep the image mode. Do not convert to RGB.
    - **Short side**: It may be below 1024. Do not clamp it.
    - **Testing Strategy**:
      - **Code Quality**: ruff and mypy, same commands as task 1.1.1
      - **Unit Testing**: `tests/unit/test_output_size.py` with `Image.new`
      - **Integration Testing**: None
      - **Test Cases**:
        - `auto` on a 1000×500 image at extent 1024 scales to 1024×512 and does not crop (the aspect stays 2:1).
        - `16:9` on a square image center-crops, then the result size is `(1024, 576)` at extent 1024.
        - `16:9` on a 2560×1440 image at extent 2048 returns `(2048, 1152)`.
        - `1:1` at extent 2048 on a 640×480 image returns `(2048, 2048)`.
        - `7:5` at extent 1024 returns the ideal `7:5` size (long side 1024).
        - A source that is already the target size is unchanged in size.
      - **Mocks/Fixtures**: Solid-color PIL images. No files.
      - **Coverage**: Auto scale, center crop, and exact saved sizes from the spec edge cases that do not need a provider.

### Task 1.2: Validate and fit inside `generate_image()` - ✅ Done
*Spec Reference: Functional Requirements, Bitmap fit, Omitted request, Technical Constraints*

- [x] 1.2.1 **Check the pair, pass it through, then fit** - ✅ Done
  - *Hint*: `generate_image()` in `src/genimg/core/image_gen.py` already raises `ValidationError` before `impl.generate`. `tests/unit/test_image_gen.py` patches the registry with `MagicMock`.
  - *Consider*: New arguments are keyword-only and default to `None`. Current callers stay valid. The fit runs only after a successful return.
  - *Files*: `src/genimg/core/image_gen.py`, `tests/unit/test_image_gen.py`
  - *Risk*: Fitting before the provider call would hide a validation bug. Call the provider only after `normalize_size_pair` returns.
  - **IMPLEMENTATION PLAN**:
    - **Signature**: Add keyword-only `aspect_ratio: str | None = None` and `max_extent: int | float | str | None = None` at the end of `generate_image()`. `normalize_size_pair` accepts a Gradio float and a blank string. After it returns, the provider receives `str | None` and `int | None` only.
    - **Order**:
      - Keep the current prompt, reference, provider, and model checks.
      - Call `normalize_size_pair` before `impl.generate`.
      - On `ValidationError`, do not call the provider.
      - Pass `aspect_ratio` and `max_extent` into `impl.generate` only when the pair is set. Pass `None` and `None` when it is omitted.
      - On success, when the pair is set, replace `result.image` with `fit_image(...)`.
      - When the pair is omitted, return the provider image unchanged.
    - **Docs string**: Mention the two arguments and that a partial pair or a bad extent raises `ValidationError`.
    - **Testing Strategy**:
      - **Code Quality**: ruff and mypy
      - **Unit Testing**: Extend `tests/unit/test_image_gen.py`
      - **Integration Testing**: None
      - **Test Cases**:
        - Omitted pair: provider is called with `aspect_ratio is None` and `max_extent is None`. Returned image size is unchanged.
        - Legal pair: provider is called with the normalized token and extent. Returned image has the fitted size.
        - Extent 1023, extent 2049, a partial pair, and token `wide` raise `ValidationError`. The provider mock is not called.
      - **Mocks/Fixtures**: Existing registry `MagicMock`. Return a `GenerationResult` whose image is a known PIL size.
      - **Coverage**: The fit gate and the "before a provider runs" rule.

### Task 1.3: Accept the pair on every provider - ✅ Done
*Spec Reference: Technical Constraints, OpenRouter and Ollama, Affected Components*

- [x] 1.3.1 **Add the two keyword-only arguments to the protocol and each `generate()`** - ✅ Done
  - *Hint*: `ImageGenerationProvider.generate` in `src/genimg/core/providers/base.py`. Implementations: `wiro.py`, `openrouter.py`, `ollama.py`, `draw_things/provider.py`, `contrib/draw_things_poc/provider.py`. Existing unit tests call `generate` positionally. Defaults keep those calls valid.
  - *Consider*: This task does not map the pair. Wiro still calls `build_run_plan` without it. Draw Things still uses preset size. OpenRouter `_build_payload` and the Ollama payload dict gain no size key.
  - *Files*:
    - `src/genimg/core/providers/base.py`
    - `src/genimg/core/providers/wiro.py`
    - `src/genimg/core/providers/openrouter.py`
    - `src/genimg/core/providers/ollama.py`
    - `src/genimg/core/providers/draw_things/provider.py`
    - `src/genimg/contrib/draw_things_poc/provider.py`
  - *Risk*: Wiro and OpenRouter each have a worker thread. The new arguments must be in the signature even when the thread closes over a payload built earlier. Forgetting the thread path makes a cancel-enabled call raise `TypeError`.
  - **IMPLEMENTATION PLAN**:
    - **Protocol**: Add `*, aspect_ratio: str | None = None, max_extent: int | None = None` after `api_key_override`.
    - **Each implementation**: Add the same keyword-only arguments. Until Phase 2 and Phase 3, bind them with `_ = (aspect_ratio, max_extent)` or an equivalent so they are unused on purpose.
    - **Wiro**: Add the arguments to `generate` and to `_generate_impl`. Forward them in both the direct call and the worker call. Do not pass them to `build_run_plan` yet.
    - **OpenRouter**: Do not pass them into `_build_payload`.
    - **Ollama**: Do not add them to the `payload` dict.
    - **Testing Strategy**:
      - **Code Quality**: ruff and mypy. mypy must accept the protocol and all five implementations.
      - **Unit Testing**: Existing provider tests stay green because the new arguments default to `None`.
      - **Integration Testing**: None
      - **Test Cases**: No new behavior test beyond the existing suites. Phase 3 and the OpenRouter payload test in Phase 3 assert that the payload stays free of size fields. Phase 1 only proves the signatures accept a call.
      - **Mocks/Fixtures**: None new.
      - **Coverage**: Signature compatibility. Behavior coverage for "payload unchanged" is Phase 3 so this phase does not claim that mapping is finished.

### Phase 1 Validation - ✅ Done
- **Acceptance Criteria**:
  - A partial pair, extent 1023, extent 2049, and token `wide` raise `ValidationError` and do not call the provider.
  - A legal pair fits the returned image. `auto` does not center-crop.
  - An omitted pair does not fit.
  - Existing provider tests still pass.
- **Testing Strategy**: `.venv/bin/pytest tests/unit/test_output_size.py tests/unit/test_image_gen.py tests/unit/test_providers_wiro.py tests/unit/test_providers_ollama.py tests/unit/test_openrouter_payload.py tests/unit/test_providers_draw_things.py` then the full `tests/unit/` suite.
- **Rollback Plan**: Delete `output_size.py` and its test. Revert the `generate_image()` and `generate()` signature edits. No config or schema migration is involved.

## Phase 2: Wiro size mapping - ✅ Done
*Incremental Goal: `build_run_plan` stops forcing `aspectRatio` to `1:1` and stops forcing reference `width` and `height` to `1024`. A set pair becomes a legal pixel body or a legal ratio body. An omitted pair copies non-empty in-range `defaultvalue` strings for the four size ids only.*

### Task 2.1: Replace `_apply_output_sizing` - ✅ Done
*Spec Reference: Wiro pixel models, Wiro ratio models, Omitted request, Technical Approach*

- [x] 2.1.1 **Skip size ids in `_static_schema_fields` and delete the square pin** - ✅ Done
  - *Hint*: `_apply_output_sizing`, `WIRO_DEFAULT_ASPECT_RATIO`, and `WIRO_REFERENCE_SQUARE_SIZE` live at the top of `src/genimg/core/providers/wiro_schema.py`. `_static_schema_fields` reads `item.get("default")`.
  - *Consider*: JSON and multipart both go through `build_run_plan`. One mapper covers both. `has_reference` must not change size.
  - *Files*: `src/genimg/core/providers/wiro_schema.py`, `src/genimg/core/providers/wiro.py`
  - *Risk*: Required non-size fields such as `maxImages` must keep today's type fallback. A size field with `required: true` and a blank `defaultvalue` is omitted on purpose.
  - **IMPLEMENTATION PLAN**:
    - **Delete**: `WIRO_DEFAULT_ASPECT_RATIO`, `WIRO_REFERENCE_SQUARE_SIZE`, and `_apply_output_sizing`.
    - **Static fields**: In `_static_schema_fields`, `continue` when `param_id` is in `WIRO_SIZE_FIELD_IDS`. Leave the `default` read and the required-param fallback in place for every other id.
    - **`build_run_plan` signature**: Add keyword-only `aspect_ratio: str | None = None` and `max_extent: int | None = None`.
    - **Call order**: Build static fields, then call one new function `apply_size_fields(items, fields, aspect_ratio, max_extent) -> dict[str, str]`.
    - **Branch**: When the pair is set, do not copy omitted `defaultvalue` entries. The pixel or ratio adapter is the only writer of the four size keys. When the pair is omitted, run only the `defaultvalue` copy from task 2.1.2.
    - **Wiro provider**: Pass `aspect_ratio` and `max_extent` from `_generate_impl` into `build_run_plan`. Remove the unused-argument binding added in task 1.3.1.
    - **Classification**:
      - An `aspectRatio` item whose `type` is `select` is a ratio model, even when `width` and `height` also exist.
      - `width` and `height` with no `aspectRatio` select is a pixel model.
      - Any other schema has no size adapter. The omitted-default copy below still runs for whichever of the four ids exist.
    - **Follow-on**: `_select_option_values` is only used by `_apply_output_sizing`. After that function is gone, leave `_select_option_values` in place if nothing calls it. Do not delete it in this phase. Record it as a follow-on.
    - **Testing Strategy**:
      - **Code Quality**: ruff and mypy
      - **Unit Testing**: Rewrite the square-pin tests in `tests/unit/test_wiro_schema.py` in the subtasks below. Keep `test_json_plan_includes_required_schema_fields` green (`maxImages`, `watermark`).
      - **Integration Testing**: Do not call live Wiro. Trust the schema passed into `build_run_plan`.
      - **Test Cases**: Covered by 2.1.2 through 2.1.4.
      - **Mocks/Fixtures**: Extend the schema dicts already in `tests/unit/test_wiro_schema.py`. Use `defaultvalue`, not `default`, on size fields.
      - **Coverage**: Both content modes, with and without a reference image.

- [x] 2.1.2 **Copy `defaultvalue` on the omitted path** - ✅ Done
  - *Hint*: Live Tool/Detail stores the playground default in `defaultvalue`. The current code reads `default`, so those values never reach the Run body.
  - *Consider*: A pixel `defaultvalue` outside a positive schema `minvalue` or `maxvalue` is omitted. Do not invent a replacement. Option objects use `value` and `text`.
  - *Files*: `src/genimg/core/providers/wiro_schema.py`, `tests/unit/test_wiro_schema.py`
  - *Risk*: Treating `minvalue` `0` as a floor would drop FLUX's `1024` default or reject a short side. `0` is not a positive integer. Ignore it.
  - **IMPLEMENTATION PLAN**:
    - **When**: `aspect_ratio` and `max_extent` are both `None`.
    - **Positive bound**: Accept `int` greater than 0, a whole `float` greater than 0, or a digit string greater than 0. Ignore bools, `0`, blanks, and missing keys.
    - **`aspectRatio` and `resolution`**: If `defaultvalue` is a non-empty string after strip, copy that string. Otherwise omit the key.
    - **`width` and `height`**: If `defaultvalue` is a non-empty string and it is inside every present positive bound on that same item, copy it. If it lies outside a present bound, omit it. If no positive bound exists, copy the non-empty string as-is.
    - **Do not read** the item `default` key for these four ids.
    - **Reference images**: Same rules with and without refs. No `1024` pin.
    - **Testing Strategy**:
      - **Unit Testing**: `tests/unit/test_wiro_schema.py`
      - **Test Cases**:
        - A ratio schema with no `defaultvalue` omits `aspectRatio` for text-only and for a reference run. This replaces `test_json_plan_t2i_sets_square_aspect_ratio`, `test_multipart_plan_with_ref_sets_square_aspect_ratio`, and `test_json_plan_without_ref_sets_square_aspect_ratio`.
        - A dimension schema with no `defaultvalue` omits `width` and `height` even when a reference is present. This replaces `test_multipart_plan_with_ref_sets_square_width_height`.
        - `defaultvalue` `"1:1"` is copied. Blank and missing `defaultvalue` are omitted.
        - Pixel `defaultvalue` `"1024"` with `maxvalue` 2048 is copied. `"4096"` with `maxvalue` 2048 is omitted. `minvalue` 0 does not reject `"1024"`.
        - A required size field with a blank `defaultvalue` is omitted. `maxImages` is still `"1"`.
        - A prompt-only schema with a legal pair still builds a plan and adds no size keys. The bitmap fit, not the Run body, makes the frame.
      - **Mocks/Fixtures**: In-memory schema dicts and the existing `MINIMAL_PNG` reference.
      - **Coverage**: Omitted path for ratio fields, pixel fields, and the required-field fallback that must stay.

- [x] 2.1.3 **Map a pair onto a pixel model** - ✅ Done
  - *Hint*: Call `ideal_pixel_size` from `output_size.py`. FLUX-style items use `minvalue` 0, `maxvalue` 2048, and `defaultvalue` `"1024"`.
  - *Consider*: This path does not raise `ValidationError` for a legal ratio. It does not send `aspectRatio` or `resolution`.
  - *Files*: `src/genimg/core/providers/wiro_schema.py`, `tests/unit/test_wiro_schema.py`
  - *Risk*: Uniform scale can satisfy one bound and break another. The fallback then sends schema max on the long side and schema min on the short side. The bitmap fit, not this function, restores the ratio.
  - **IMPLEMENTATION PLAN**:
    - **Start**: `width, height = ideal_pixel_size(aspect_ratio, max_extent)`. `auto` is already a square from that helper.
    - **Bounds**: Read positive `minvalue` and `maxvalue` on the `width` item and the `height` item. Also keep the long side inside `MIN_OUTPUT_EXTENT` through `MAX_OUTPUT_EXTENT`.
    - **Scale**: If the ideal pair breaks a bound, compute the uniform scale window. Each present max contributes an upper scale of `bound / side`. Each present min contributes a lower scale of `bound / side`. The long-side window contributes the same against 1024 and 2048.
      - If the lower scale is less than or equal to the upper scale, use the scale inside that window that is closest to `1`. Round each side with `round_half_away_from_zero`.
      - If rounding breaks a bound, or the scale window is empty, use the fallback.
    - **Fallback**: Long side becomes the positive `maxvalue` of the long-side field. Short side becomes the positive `minvalue` of the short-side field. Use this pair only when both of those bounds exist. The result may be a different ratio. Do not raise.
    - **Body**: Set `width` and `height` to decimal strings. Do not set `aspectRatio` or `resolution`. Remove those keys if a previous step added them.
    - **Testing Strategy**:
      - **Unit Testing**: `tests/unit/test_wiro_schema.py`
      - **Test Cases**:
        - `1:1` at 2048 with max 2048 sends `"2048"` and `"2048"`.
        - `16:9` at 1024 sends `"1024"` and `"576"` even though the short side is below 1024.
        - `auto` at 1024 sends `"1024"` and `"1024"`.
        - `minvalue` 0 is ignored.
        - A schema max of 1536 on a `1:1` request at 2048 sends `"1536"` and `"1536"`.
        - Impossible floor and ceiling (min 1024, max 1280, ratio `16:9`) sends long side `"1280"` and short side `"1024"`.
        - The body has no `aspectRatio` and no `resolution`.
        - The same pixel strings appear in JSON fields and in multipart text fields.
      - **Mocks/Fixtures**: Pixel schema dicts with and without a file input.
      - **Coverage**: Ideal pair, schema max scale-down, and the floor/ceiling fallback.

- [x] 2.1.4 **Map a pair onto a ratio model and parse frames** - ✅ Done
  - *Hint*: Test schemas in `tests/unit/test_wiro_schema.py` already use option dicts with `value` and `text`. Add texts in the Seedream colon form (`2k: 2560x1440`) and the Nano Banana parenthesis form (`(1K)1376x768`).
  - *Consider*: Do not send `width` or `height` on this path. Do not raise because a tier is larger than `max_extent`. Do not hard-code bundled model option lists.
  - *Files*: `src/genimg/core/providers/wiro_schema.py`, `tests/unit/test_wiro_schema.py`
  - *Risk*: Frame text that has no tier token must use the nominal `<number>k` times 1024 rule, not a guessed pixel size. A failed parse omits `resolution`.
  - **IMPLEMENTATION PLAN**:
    - **Aspect match**, in order:
      - Token `auto`: option whose `value` equals `auto` (ignore case). Else option whose `text` equals `auto`. Else option whose `text` equals `Match Input Image`. Send that option's `value`, including `""`.
      - If `auto` matches none of those three, do not compute a distance. `auto` has no quotient. Send `defaultvalue` when it is a non-empty string. Otherwise send the first option `value`. Do not raise.
      - Any other token that equals an option `value` (ignore case) sends that option's stored spelling.
      - Otherwise pick the closest numeric option. A numeric option is a `value` or, if the value is not `W:H`, a `text` that matches `^\d+:\d+$` with positive parts. Distance is the absolute difference of the two width/height quotients. A tie keeps the earlier option.
      - When no option is numeric, send `defaultvalue` when it is a non-empty string. Otherwise send the first option `value`.
    - **Do not send** `width` or `height`.
    - **Frame parser** `resolution_frames(text: str) -> list[tuple[str, int]]`:
      - Read every tier in these two shapes, case-insensitive, with `x` or `×`:
        - `<number>k: <width>x<height>`
        - `(<number>k)<width>x<height>`
      - The long side is `max(width, height)`.
      - Return `(tier_token, long_side)` in text order.
    - **Resolution choice** when the matched aspect `text` has at least one frame:
      - Match each tier token to a `resolution` option `value` (ignore case).
      - Keep the option's stored spelling.
      - Ignore a frame whose tier matches no resolution option.
      - If at least one frame matches, send the option whose long side is closest to `max_extent`.
      - Tie-break: smaller distance, then prefer `long_side <= max_extent`, then the earlier option.
      - If no frame matches an option, omit `resolution`.
    - **No frames in the aspect text**:
      - A resolution `value` that matches `^(?i)(\d+(?:\.\d+)?)k$` has nominal long side `number * NOMINAL_K_PIXELS`.
      - Use the same closest-side rule.
      - `2k` is 2048. `4k` is 4096. `3k` is 3072. `1K` is 1024.
    - **Nothing readable**: Omit `resolution`.
    - **Testing Strategy**:
      - **Unit Testing**: `tests/unit/test_wiro_schema.py`. Test the frame parser directly.
      - **Test Cases**:
        - `16:9` matches value `16:9` and sends that spelling.
        - `7:5` against options `1:1` then `16:9` sends `1:1`, because `|7/5 - 1|` is smaller than `|7/5 - 16/9|`.
        - Two numeric options with the same distance: the earlier option is sent.
        - `auto` with value `""` and text `auto` sends `""`.
        - `auto` with text `Match Input Image` sends that option value when no `auto` value or text exists.
        - `auto` with no auto option and no Match Input Image text sends `defaultvalue` when that string is non-empty, otherwise the first option `value`.
        - Aspect text `2k: 2560x1440, 4k: 3840x2160` at extent 2048 sends the resolution value for the 2560 tier.
        - Aspect text with frames 1920 and 2880 at extent 2048 sends the 1920 tier.
        - Equal distance (1024 and 3072 at extent 2048) sends the 1024 tier.
        - Parenthesis form `(1K)1376x768` is parsed.
        - Aspect text with no frames and resolution values `2k` and `4k` at extent 2048 sends `2k`.
        - No resolution tiers: the key is absent.
        - A ratio model that also has `width` and `height` does not send those keys when the pair is set.
        - Caller spelling `16:9` against schema value `16:9` is unchanged. Caller spelling that differs only by case sends the schema spelling.
      - **Mocks/Fixtures**: Inline option lists. No copied live catalogs.
      - **Coverage**: Auto empty value, closest ratio, both frame shapes, nominal `k`, tie that does not exceed the extent, and omitted resolution.

- [x] 2.1.5 **Expose aspect choices from a schema** - ✅ Done
  - *Hint*: Gradio in Phase 5 needs labels and values without a second parser.
  - *Consider*: The fixed list is the caller-facing fallback. It is not a Wiro option list.
  - *Files*: `src/genimg/core/providers/wiro_schema.py`, `tests/unit/test_wiro_schema.py`
  - *Risk*: A blank option value must not become the Gradio value, because Phase 1 treats a blank aspect string as omitted.
  - **IMPLEMENTATION PLAN**:
    - **Function**: `aspect_choices_from_schema(schema: dict) -> list[tuple[str, str]] | None`
    - **Return `None`** when the schema has no `aspectRatio` select. The UI then uses `FIXED_ASPECT_RATIOS`.
    - **Return rows** `(label, submit_value)` for each option:
      - Label is `text` when it is a non-empty string, otherwise the `value` string.
      - Submit value is the option `value` string when that string is non-empty.
      - When `value` is blank and `text` is `auto` or `Match Input Image` (ignore case), submit value is `auto`.
    - **Do not** include the Model default row. The UI adds that row.
    - **Testing Strategy**:
      - **Unit Testing**: One test with a select, one test with only width and height (`None`), one test whose auto value is `""`.
      - **Test Cases**: Label is `text`. Non-empty value is preserved. Blank auto value becomes submit token `auto`.
      - **Mocks/Fixtures**: Small schema dicts.
      - **Coverage**: Ratio schema, pixel schema, blank auto value.

### Phase 2 Validation - ✅ Done
- **Acceptance Criteria**:
  - A call with no size arguments does not set Wiro `aspectRatio` to `1:1` and does not set reference `width` and `height` to `1024` unless that string is an in-range `defaultvalue`.
  - FLUX-style `1:1` at 2048 sends `2048` and `2048`. `16:9` at 1024 sends `1024` and `576`.
  - A `16:9` model whose published long sides are 2560 and 3840 sends the 2560 tier at extent 2048.
  - `7:5` does not raise. It snaps to the closest option value.
  - Required non-size fields still receive today's fallback.
- **Testing Strategy**: `.venv/bin/pytest tests/unit/test_wiro_schema.py tests/unit/test_wiro_client.py tests/unit/test_providers_wiro.py` then `tests/unit/`.
- **Rollback Plan**: Restore `_apply_output_sizing` and the two constants from git. Revert the `build_run_plan` arguments. Wiro `generate()` can keep accepting the pair and ignore it, which is the Phase 1 behavior.

## Phase 3: Draw Things canvas and unchanged payloads - ✅ Done
*Incremental Goal: Draw Things requests a 64-pixel canvas for the pair and leaves the preset alone when the pair is omitted. OpenRouter and Ollama payloads gain no size field.*

### Task 3.1: Snap the Draw Things canvas for one run - ✅ Done
*Spec Reference: Draw Things, Technical Constraints*

- [x] 3.1.1 **Override width and height after preset resolution** - ✅ Done
  - *Hint*: `DrawThingsProvider._resolve_tuning` applies `draw_things_width_px` and `draw_things_height_px` after the preset. `tests/unit/test_providers_draw_things.py` captures kwargs with `_CaptureClient`. `round_dimension_to_multiple_of_64` is in `src/genimg/core/providers/draw_things/config_builder.py`. The grid and the minimum side are 64 (`LAYOUT_BLOCK_PX`, `MIN_DIMENSION_PX`).
  - *Consider*: The rounded pair replaces preset width and height for this run only. Other tuning (steps, sampler, LoRA) stays. Do not mutate `Config`.
  - *Files*: `src/genimg/core/providers/draw_things/provider.py`, `tests/unit/test_providers_draw_things.py`
  - *Risk*: Applying the override before `_resolve_tuning` lets `GENIMG_DRAW_THINGS_WIDTH_PX` win. The spec says those variables apply only when the pair is omitted.
  - **IMPLEMENTATION PLAN**:
    - **After** `tuning = self._resolve_tuning(config)`:
      - If both size arguments are set, compute `ideal_pixel_size`, then `round_dimension_to_multiple_of_64` on each side.
      - Assign those ints to local `tuning.width_px` and `tuning.height_px`.
      - If the pair is omitted, leave `tuning` as `_resolve_tuning` built it.
    - **Pass** the tuning width and height into `generate_image_last_tensor` as today.
    - **Remove** the unused-argument binding from Phase 1.
    - **Testing Strategy**:
      - **Code Quality**: ruff and mypy
      - **Unit Testing**: Add cases next to `test_provider_uses_preset_defaults` using `_CaptureClient`.
      - **Integration Testing**: None. Do not call gRPC.
      - **Test Cases**:
        - Omitted pair with preset `z-image` still sends `width_px` 1280 and `height_px` 1280.
        - Omitted pair with `draw_things_width_px` set still sends that env value.
        - `16:9` at 2048 sends the 64-pixel grid near 2048×1152. `ideal_pixel_size` is `(2048, 1152)`. Both sides are already multiples of 64, so the client receives 2048 and 1152.
        - A side that is not a multiple of 64 is rounded by `round_dimension_to_multiple_of_64`.
        - `auto` at 1024 sends a square grid (1024×1024).
        - Steps and LoRA from the preset stay on the captured kwargs.
      - **Mocks/Fixtures**: Existing `_CaptureClient` and `dt_tensor_bytes_to_pil` monkeypatch.
      - **Coverage**: Omitted preset, env width, and an explicit pair. The saved-image fit is already covered in Phase 1. This task covers the canvas the provider sends.

- [x] 3.1.2 **Map the contrib Draw Things provider the same way** - ✅ Done
  - *Hint*: `src/genimg/contrib/draw_things_poc/provider.py` uses constructor `self._width_px` and `self._height_px`. It has its own `round_dimension_to_multiple_of_64` in `contrib/draw_things_poc/config_builder.py`. It already imports `Config` and `GenerationResult` from core.
  - *Consider*: This provider is not in the registry. `generate_image()` does not call it. The spec still requires the same arguments and the same canvas math.
  - *Files*: `src/genimg/contrib/draw_things_poc/provider.py`, `tests/test_draw_things_poc.py`
  - *Risk*: Writing `self._width_px` would change the next run. Use locals for this call only.
  - **IMPLEMENTATION PLAN**:
    - **Signature**: Already added in task 1.3.1. Use the arguments.
    - **When the pair is set**: Local width and height come from `ideal_pixel_size` and the contrib `round_dimension_to_multiple_of_64`. Pass those locals to `generate_image_last_tensor`.
    - **When the pair is omitted**: Pass `self._width_px` and `self._height_px` as today.
    - **Import** `ideal_pixel_size` from `genimg.core.output_size`. Do not import the core Draw Things package into the contrib tree.
    - **Testing Strategy**:
      - **Unit Testing**: Follow the existing poc provider tests around `tests/test_draw_things_poc.py` (they call `prov.generate` with a stub). Assert the width and height passed into the client.
      - **Test Cases**:
        - Omitted pair keeps constructor 512×512 (the constructor default) or whatever the test constructed.
        - `1:1` at 1024 passes 1024 and 1024.
        - A second call without the pair still uses the constructor size.
      - **Mocks/Fixtures**: Existing poc stub client.
      - **Coverage**: One-run override and no leaked state.

### Task 3.2: Prove OpenRouter and Ollama add no size field - ✅ Done
*Spec Reference: OpenRouter and Ollama, Out of Scope*

- [x] 3.2.1 **Assert the payloads stay unchanged** - ✅ Done
  - *Hint*: `OpenRouterProvider._build_payload` returns `model`, `modalities`, and `messages` only. Ollama `generate()` builds `{"model", "prompt", "stream", "think"}`. Tests live in `tests/unit/test_openrouter_payload.py` and `tests/unit/test_providers_ollama.py`.
  - *Consider*: Do not add an OpenRouter `image_config` field. The bitmap fit in `generate_image()` is what makes the saved image match.
  - *Files*: `tests/unit/test_openrouter_payload.py`, `tests/unit/test_providers_ollama.py`. Touch the providers only if task 1.3.1 left a path that could copy the pair into the payload.
  - *Risk*: A later edit might pass the pair into `_build_payload`. The test should call the public `generate` path or assert `_build_payload` still has three parameters and the body keys are unchanged.
  - **IMPLEMENTATION PLAN**:
    - **OpenRouter**: Call `_build_payload` and assert the keys are only `model`, `modalities`, and `messages`. Add a `generate(..., aspect_ratio="16:9", max_extent=1024)` test that mocks `requests` the same way `test_providers_ollama.py` does, and assert the posted JSON has no `width`, `height`, `aspect_ratio`, `aspectRatio`, `resolution`, or `image_config`.
    - **Ollama**: Same assertion on the posted JSON for a generate call that includes the pair.
    - **Testing Strategy**:
      - **Unit Testing**: The two files above.
      - **Integration Testing**: None
      - **Test Cases**: One OpenRouter post and one Ollama post, each with a legal pair, each with a payload free of size fields.
      - **Mocks/Fixtures**: `unittest.mock` on `requests`, matching the existing provider tests.
      - **Coverage**: The out-of-scope `image_config` key as well as the four Wiro size names.

### Phase 3 Validation - ✅ Done
- **Acceptance Criteria**:
  - Draw Things receives a 64-pixel canvas for the pair. An omitted pair still uses the preset and the Draw Things env size.
  - OpenRouter and Ollama payloads gain no size field.
  - Contrib constructor size survives a later omitted call.
- **Testing Strategy**: `.venv/bin/pytest tests/unit/test_providers_draw_things.py tests/unit/test_openrouter_payload.py tests/unit/test_providers_ollama.py tests/test_draw_things_poc.py` then `tests/unit/`.
- **Rollback Plan**: Ignore the pair again inside both Draw Things `generate()` methods. Payload tests can stay. They document current behavior.

## Phase 4: CLI flags - ✅ Done
*Incremental Goal: `genimg generate` and `genimg character` accept `--aspect-ratio` and `--max-extent`, reject a bad pair with `ValidationError`, and do not grow an environment variable.*

### Task 4.1: Pass the flags into `generate_image()` - ✅ Done
*Spec Reference: Functional Requirements, Technical Constraints, Edge Cases & Error Handling*

- [x] 4.1.1 **Add the options to both commands** - ✅ Done
  - *Hint*: Click options are stacked above `generate()` and `character()` in `src/genimg/cli/commands.py`. `--api-key` sets `envvar`. These two options must not. `tests/unit/test_cli.py` uses `CliRunner` and `_invoke_generate` / character helpers. Help tests only assert that `draw_things` appears.
  - *Consider*: Do not add `--width`, `--height`, or `--resolution`. Do not use `click.IntRange`. An out-of-range extent must be `ValidationError` from `generate_image()`, not a Click usage error. Non-integer text may still be a Click error. That is outside the spec cases.
  - *Files*: `src/genimg/cli/commands.py`, `tests/unit/test_cli.py`
  - *Risk*: `character` merges references before generation. Pass the flags only into `generate_image()`. Do not change `merge_jpeg_base64_references_horizontally` or `process_reference_image`.
  - **IMPLEMENTATION PLAN**:
    - **Options** on both commands, with no `envvar`:
      - `--aspect-ratio`, default `None`, help text that names `16:9` and `auto` and says `--max-extent` is required with it.
      - `--max-extent`, `type=int`, default `None`, help text that says the longer side is from 1024 through 2048.
    - **Forward**: Add `aspect_ratio` and `max_extent` to the `gen_kw` dict in `generate` and in `character` when building the `generate_image()` call. Pass `None` through. `normalize_size_pair` treats `""` as omitted.
    - **Do not** add the flags to `genimg ui` or to the contrib Draw Things CLI.
    - **Testing Strategy**:
      - **Code Quality**: ruff and mypy
      - **Unit Testing**: `tests/unit/test_cli.py` with `generate_image` patched, same pattern as the existing generate tests.
      - **Integration Testing**: None
      - **Test Cases**:
        - `genimg generate --help` and `genimg character --help` contain `--aspect-ratio` and `--max-extent`.
        - Help text does not contain `--width`, `--height`, or `--resolution` as options. Check the option lines, not the Draw Things tuning prose if that prose mentions width.
        - A quiet generate with both flags calls `generate_image` with `aspect_ratio="16:9"` and `max_extent=2048`.
        - `--aspect-ratio ""` calls `generate_image` with a blank or `None` aspect and does not by itself raise.
        - `--aspect-ratio 16:9` without `--max-extent` exits non-zero and the provider is not called. The error is `ValidationError` (assert the message or the exception type via the existing error handler).
        - `--max-extent 2048` without `--aspect-ratio` exits non-zero the same way.
        - `--max-extent 1023` and `--max-extent 2049` exit non-zero before the provider.
        - The same pair reaches `generate_image` from `genimg character`.
        - Option definitions have no `envvar`. Assert with `cli.commands["generate"].params` and the character command.
      - **Mocks/Fixtures**: Patch `generate_image`. Use the existing tiny PNG reference for character.
      - **Coverage**: Both commands, help text, partial pair, bad extent, and no env var.

### Phase 4 Validation - ✅ Done
- **Acceptance Criteria**:
  - Both commands accept the two flags and pass them through.
  - A partial pair and extents 1023 and 2049 fail before a provider runs.
  - No new environment variable exists.
- **Testing Strategy**: `.venv/bin/pytest tests/unit/test_cli.py` then `tests/unit/`.
- **Rollback Plan**: Remove the two options and the `gen_kw` keys. Library behavior from Phases 1–3 stays.

## Phase 5: Gradio Output size block - ✅ Done
*Incremental Goal: The generate form shows an Output size row under the provider and model row. The row has an aspect dropdown and a max-extent number for every provider. Wiro schema choices replace the fixed list when the schema loads. A failed load keeps the fixed list and shows the error. A still-valid aspect is kept. Existing handler tests keep working.*

### Task 5.1: Load schema choices through the existing cache - ✅ Done
*Spec Reference: Functional Requirements, Technical Constraints, Edge Cases & Error Handling*

- [x] 5.1.1 **Add a cache-backed schema lookup** - ✅ Done
  - *Hint*: `_schema_cache` and `WiroProvider._cached_schema` are in `src/genimg/core/providers/wiro.py`. `WiroClient.get_model_detail` fills the cache. The UI must not create a second dict.
  - *Consider*: A custom model id that Tool/Detail cannot load uses the fixed list. Generation still uses the existing Wiro error path later, when the user clicks Generate.
  - *Files*: `src/genimg/core/providers/wiro.py`, `src/genimg/ui/gradio_app.py`
  - *Risk*: A cold cache calls Wiro on each model change. That is accepted. Do not prefetch every bundled model.
  - **IMPLEMENTATION PLAN**:
    - **Function** on the Wiro module, for example `load_cached_model_schema(config: Config, model: str) -> dict`:
      - Parse `owner/model` with `parse_model_slugs`.
      - Build a `WiroClient` the same way `WiroProvider._client` does.
      - Read and fill `_schema_cache` through `_cached_schema`. Do not add another cache dict.
    - **UI helper** `output_size_choices(provider: str, model: str | None) -> tuple[list[tuple[str, str]], str | None]`:
      - First row is `(MODEL_DEFAULT_LABEL, "")`.
      - Non-Wiro providers: remaining rows are `(ratio, ratio)` from `FIXED_ASPECT_RATIOS`. Error is `None`.
      - Wiro: call `load_cached_model_schema`. On success, if `aspect_choices_from_schema` returns rows, append those rows. If it returns `None`, append the fixed list.
      - On `ValidationError`, `APIError`, `NetworkError`, or `RequestTimeoutError`, append the fixed list and return the existing user-facing message (`_exception_to_message`).
    - **Testing Strategy**:
      - **Unit Testing**: `tests/unit/test_gradio_app.py` for the helper. Patch `load_cached_model_schema`.
      - **Test Cases**:
        - OpenRouter returns Model default plus the ten fixed ratios and no error.
        - Wiro schema with an `aspectRatio` select returns Model default plus schema rows. Labels are option text.
        - A schema with a blank auto value submits `auto`, not `""`.
        - A pixel schema returns the fixed list.
        - A raised `APIError` returns the fixed list and a non-empty error string.
      - **Mocks/Fixtures**: Schema dicts from Phase 2. No live HTTP.
      - **Coverage**: Every provider class uses the same visible block. The helper's provider branch is the test. Wiro, and one non-Wiro id, are enough if the non-Wiro branch does not special-case OpenRouter.

### Task 5.2: Add the form block and append handler arguments - ✅ Done
*Spec Reference: Functional Requirements, Technical Constraints*

- [x] 5.2.1 **Place the Output size row under the model row and rebuild choices** - ✅ Done
  - *Hint*: The provider and model dropdowns share one `gr.Row` in `_build_blocks` in `src/genimg/ui/gradio_app.py`. `ref_message` and `lora_section` are nested in the model column today. `_on_provider_change` returns updates for `model_dd`, `ref_message`, and the LoRA slots. `tests/unit/test_gradio_app.py` calls `_run_generate` and `_generate_click_handler` positionally and does not call `_on_provider_change`.
  - *Consider*: The block stays visible for every provider, including after a schema error. Do not add width, height, or resolution controls. Do not use a slider. Do not prefill 1024. New handler arguments are appended and default to empty so current tests stay valid.
  - *Files*: `src/genimg/ui/gradio_app.py`, `tests/unit/test_gradio_app.py`
  - *Risk*: Growing `_on_provider_change`'s return tuple without updating `provider_dd.change` outputs will mis-assign LoRA updates. Append the new outputs at the end of that tuple and of the `outputs` list. A provider change also updates the model, and Gradio may fire `model_dd.change` as well. Both handlers must use the same retain helper so the second call does not clear a value the first call kept.
  - **IMPLEMENTATION PLAN**:
    - **Page order** inside `_build_blocks`. The model column keeps only `model_dd`.
      1. Existing row: Image provider, Image model.
      2. `gr.Markdown("Output size")`.
      3. New row, always visible. Aspect column `scale=2`. Max-extent column `scale=1`. Name those scales `OUTPUT_SIZE_ASPECT_SCALE` and `OUTPUT_SIZE_EXTENT_SCALE` next to the other UI constants in `gradio_app.py`.
      4. `ref_message`, full width, still hidden except when the provider has no reference support.
      5. `lora_section`, full width, still hidden except for Draw Things. Keep the same LoRA dropdowns and sliders. Do not restyle them.
      6. Generate and Stop stay where they are.
    - **Widgets** on the size row:
      - `gr.Dropdown` label `Aspect ratio`. `info` is `Model default keeps the provider size. A ratio needs a max extent.` Choices start with Model default plus `FIXED_ASPECT_RATIOS`. Value is `""` (Model default). `auto` stays a separate choice. Do not merge it with Model default.
      - `gr.Number` label `Max extent`. `minimum=MIN_OUTPUT_EXTENT`, `maximum=MAX_OUTPUT_EXTENT`, `precision=0`, `value=None`. `info` is `Longer side, in pixels.` Leave the number empty. An empty number plus Model default omits the pair. A prefilled 1024 plus Model default is a partial pair.
    - **Retain helper** `retain_output_size(aspect_value, max_extent, choices) -> tuple[str, object | None]`:
      - `choices` are the `(label, value)` rows from `output_size_choices`, including Model default.
      - When `aspect_value` is `None` or `""`, treat it as Model default. That value is always in the list, so keep the current extent.
      - When the current aspect value is still one of the choice values, return that value and the current extent.
      - Otherwise return `("", None)`. Clearing only the aspect would leave a partial pair.
    - **Provider change**: Add the current aspect and the current extent to the inputs. The handler already chooses the new model. Call `output_size_choices` for that provider and model, then `retain_output_size`. Append two updates after the LoRA updates: the aspect dropdown (`choices` plus the retained value) and the max-extent number (retained value, or `None` on reset). Update the `outputs` list to match. Keep the size row visible.
    - **Model change**: `model_dd.change` takes provider, model, current aspect, and current extent. It uses the same two helpers. On a fetch error, `output_size_choices` returns the fixed list and an error string. Set `status_html` to that error. On success, return `gr.update()` for the status so a previous "Done" line is left alone. Do not disable Generate. Apply retain against the list that was actually returned, including the fixed list after an error.
    - **Initial value**: On first build, call `output_size_choices` for the default provider and model. The code default provider is `ollama`, so that call uses the fixed list and does not touch Wiro. The initial aspect is Model default and the initial extent is empty, even when the helper returns schema rows. If the environment provider is Wiro, the helper may call Tool/Detail. Catch the same errors as `output_size_choices` and keep the fixed list. Do not fail `_build_blocks`.
    - **Existing test**: `test_build_blocks_returns_blocks` builds the form with the real environment. Patch `load_cached_model_schema` in that test so a local Wiro provider does not call the network.
    - **Handlers**: Append arguments:
      - `_generate_click_handler(..., aspect_ratio: str = "", max_extent: float | int | str | None = None)`
      - `_run_generate_stream` and `_run_generate` get the same two arguments at the end, with the same defaults.
      - The click `inputs` list appends the aspect dropdown and the max-extent number after the LoRA sliders.
      - Pass the two values from the click handler into `_run_generate_stream`, then into `generate_image(aspect_ratio=..., max_extent=...)`.
    - **Empty values**: `""` and `None` go through as omitted. Do not coerce Model default into `1:1`. A selected ratio plus an empty extent is a partial pair. `generate_image()` raises, and the existing `ValidationError` handler shows it on the status line. Schema errors use that same status line. Do not add a second error under the dropdown.
    - **Testing Strategy**:
      - **Code Quality**: ruff and mypy
      - **Unit Testing**: `tests/unit/test_gradio_app.py`
      - **Integration Testing**: Do not start the UI server.
      - **Test Cases**:
        - Existing positional `_run_generate(...)` and `_generate_click_handler(...)` calls still pass.
        - `_run_generate` with `aspect_ratio="16:9"` and `max_extent=1024` forwards those keywords to `generate_image`.
        - `_run_generate` with the defaults calls `generate_image` with an omitted pair (`None` or `""` normalized by the library).
        - `retain_output_size("16:9", 2048, choices)` keeps both when `16:9` is still a choice value.
        - `retain_output_size("16:9", 2048, choices)` returns `("", None)` when `16:9` is absent.
        - `retain_output_size("", 2048, choices)` keeps Model default and the extent.
        - `retain_output_size("auto", 1024, choices)` keeps `auto` when the fixed list is in use. Model default remains a different value (`""`).
        - `_build_blocks()` still returns Blocks. If the component tree is easy to walk, assert the labels `Output size`, `Aspect ratio`, and `Max extent` exist. If it is not, the helper tests plus the handler forward test are the gate.
      - **Mocks/Fixtures**: Existing `generate_image` patch in the Gradio tests. Patch schema load so `_build_blocks` does not call Wiro.
      - **Coverage**: Appended defaults, forwarded pair, retain versus reset, and visible fallback choices.

### Phase 5 Validation - ✅ Done
- **Acceptance Criteria**:
  - The Output size row sits under the provider and model row and above the LoRA block.
  - The row shows aspect ratio and max extent for every provider. It starts on Model default with an empty extent.
  - Wiro schema choices replace the fixed list when the schema loads.
  - A failed load keeps the fixed list and the status line can show the error.
  - A current aspect that is still in the new list is kept, together with the extent. Any other aspect resets both controls.
  - The reference warning and the LoRA block are full width under that row. LoRA widgets are unchanged.
  - Existing Gradio unit tests that call the handlers stay valid.
  - No second schema cache exists.
- **Testing Strategy**: `.venv/bin/pytest tests/unit/test_gradio_app.py` then `tests/unit/`. Do not start the app server. Browser click-through is not part of this gate.
- **Rollback Plan**: Remove the size row, move `ref_message` and `lora_section` back into the model column, and remove the change-handler outputs and the appended arguments. Phase 1–4 library and CLI behavior stays.

## Phase 6: Docs - ✅ Done
*Incremental Goal: README and the unreleased changelog describe the pair, the per-provider mapping, and the end of the forced `1:1` default.*

### Task 6.1: Update the user-facing notes - ✅ Done
*Spec Reference: Affected Components, Acceptance Criteria, Out of Scope*

- [x] 6.1.1 **Replace the unreleased Wiro note and document the flags** - ✅ Done
  - *Hint*: `docs/CHANGELOG.md` unreleased Changed section says Wiro text-to-image defaults `aspectRatio` to `1:1`. README CLI examples start near the "Command Line Interface" heading. The library example is the "As a Python Library" section.
  - *Consider*: Do not add an environment variable sample. Do not document `--width`. Mention that the saved image matches the request and that the model request is the nearest legal frame.
  - *Files*: `docs/CHANGELOG.md`, `README.md`
  - *Risk*: Leaving the old unreleased bullet would document the behavior this feature removes.
  - **IMPLEMENTATION PLAN**:
    - **Changelog**: Remove the unreleased bullet that says Wiro payloads default `aspectRatio` to `1:1`. Add an unreleased Changed bullet for the size pair: CLI flags, `generate_image()` arguments, Gradio block, Wiro schema mapping, Draw Things 64-pixel canvas, and bitmap fit. State that an omitted pair uses schema `defaultvalue` and no longer forces `1:1` or reference `1024`.
    - **README**:
      - Document `--aspect-ratio` and `--max-extent` on `genimg generate` and `genimg character`.
      - State the extent bounds and that both flags are required together.
      - State the per-provider behavior in a short list: Wiro uses schema options or pixels, Draw Things snaps to 64, OpenRouter and Ollama have no size field, and the saved image is fitted to the request.
      - Show one library call with `aspect_ratio` and `max_extent`.
      - State that `GENIMG_DRAW_THINGS_WIDTH_PX` and `GENIMG_DRAW_THINGS_HEIGHT_PX` apply only when the pair is omitted.
      - State that reference padding still uses `Config.aspect_ratio`.
    - **Testing Strategy**:
      - **Code Quality**: No code change. Re-run the Phase 5 unit suite if a docstring-only code comment was edited. README and changelog do not need pytest.
      - **Unit Testing**: None
      - **Integration Testing**: None
      - **Test Cases**: Read the two docs and confirm the old `1:1` unreleased claim is gone.
      - **Mocks/Fixtures**: None
      - **Coverage**: Flags, bounds, omitted path, and the four providers.

### Phase 6 Validation - ✅ Done
- **Acceptance Criteria**:
  - The unreleased changelog no longer says Wiro defaults `aspectRatio` to `1:1`.
  - README documents the two flags and the per-provider behavior.
  - `.venv/bin/ruff check src/ tests/`, `.venv/bin/mypy src/`, and `.venv/bin/pytest tests/unit/` pass.
- **Testing Strategy**: Run the three commands once after the doc edit.
- **Rollback Plan**: Revert the two doc files. Code from earlier phases stays.

## Critical Considerations
- **Performance**: The fit is one crop and one Lanczos resize of a single image. A cold Wiro schema fetch on model change is one Tool/Detail call, then the process cache. Do not prefetch.
- **Security**: No new secret, env var, or endpoint. Schema text is display labels and parse input. Do not evaluate it.
- **Scalability**: One in-process schema cache already exists. This feature adds no store and no background job.
- **Monitoring**: No new metrics. Existing Wiro and provider logs stay. Validation failures surface as `ValidationError` on the CLI and as the Gradio status line.
- **Cross-Phase Dependencies**:
  - Phase 2 and Phase 3 import `ideal_pixel_size` from Phase 1.
  - Phase 3 payload tests assume Phase 1 signatures.
  - Phase 4 calls `generate_image()` from Phase 1.
  - Phase 5 calls `aspect_choices_from_schema` from Phase 2 and `load_cached_model_schema` added in Phase 5.
  - Phase 6 describes the finished behavior and should not land before Phase 5.

## Specification Coverage
- Pair shape, blank string, both-or-neither, extent bounds, and token rules: Tasks 1.1 and 1.2.
- CLI flags and no `--width` / `--height` / `--resolution`: Task 4.1.
- `generate_image()` arguments, provider call, then fit: Tasks 1.2 and 1.3.
- Gradio block, fixed list, schema labels, failed fetch, row layout, and retain-or-reset: Tasks 5.1 and 5.2.
- Wiro pixel math, schema clamp, fallback: Task 2.1.3.
- Wiro ratio match, closest option, frame parser, nominal `k`: Task 2.1.4.
- Draw Things 64-pixel canvas and env size only when omitted: Task 3.1.
- OpenRouter and Ollama payloads unchanged, fit still applied: Tasks 1.2 and 3.2.
- Omitted Wiro path, `defaultvalue`, no forced `1:1` or `1024`: Task 2.1.2.
- No new env var or `Config` field: Tasks 1.1, 3.1, and 4.1.
- Reference padding and character merge unchanged: Task 4.1 does not edit them.
- Tests, README, changelog: Tasks 2.1, 3.1, 3.2, 4.1, 5.2, and 6.1.

## Research & Validation Completed
- **Dependencies Verified**:
  - Pillow is already used (`Image.open`, `Image.new`). `Image.Resampling.LANCZOS` is the fit filter. No new dependency.
  - `round_dimension_to_multiple_of_64` exists in `src/genimg/core/providers/draw_things/config_builder.py` and in `src/genimg/contrib/draw_things_poc/config_builder.py`. Grid and minimum are 64.
  - `ModelRunPlan` field dicts are `dict[str, str]`. `WiroClient.run_model` posts `plan.json_fields` as JSON and `plan.multipart_text_fields` as multipart data.
  - The Wiro schema cache is the module dict `_schema_cache` in `src/genimg/core/providers/wiro.py`, filled by `WiroProvider._cached_schema` via `WiroClient.get_model_detail`.
  - Lint and test commands are `.venv/bin/ruff`, `.venv/bin/mypy`, and `.venv/bin/pytest`.
- **Patterns Identified**:
  - Provider `generate()` methods already take `api_key_override` as keyword-only with a default. The new arguments follow that pattern.
  - `generate_image()` validates, then calls `impl.generate`. The fit belongs after that call.
  - Gradio handlers already append later arguments with defaults. `_generate_click_handler` tests pass eight positionals. `_run_generate` tests pass five. Appending defaults keeps those calls valid.
  - The provider and model dropdowns share one row. `ref_message` and `lora_section` are nested in the model column. Phase 5 moves those two containers below the new Output size row.
  - Draw Things provider tests capture client kwargs with `_CaptureClient` and do not open a socket.
  - Wiro schema tests build inline Tool/Detail dicts and call `build_run_plan` directly.
- **Assumptions Validated**:
  - No current `generate()` implementation other than the five named in the spec. `image_analysis` `model.generate` is unrelated.
  - No code reads `WIRO_DEFAULT_ASPECT_RATIO` or `WIRO_REFERENCE_SQUARE_SIZE` outside `wiro_schema.py`.
  - The only tests that expect a forced `1:1` or a reference `1024` are in `tests/unit/test_wiro_schema.py`.
  - `docs/CHANGELOG.md` unreleased Changed section is the note to replace.
  - Reference padding stays in `process_reference_image` and `Config.aspect_ratio`. This plan does not edit `src/genimg/core/reference.py` or `src/genimg/core/config.py`.
