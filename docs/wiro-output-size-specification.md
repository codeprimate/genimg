# Feature: Output size on the CLI, library, and web UI

## Problem Statement

Wiro image models expose output size in the Tool/Detail schema. Ratio models use an `aspectRatio` select and a `resolution` select. Pixel models use `width` and `height` numbers. The allowed values differ per model. Seedream 4.5 offers `2k` and `4k`. Seedream v5 Lite offers `2k` and `3k`. Nano Banana Pro offers `1K`, `2K`, and `4K`. FLUX.1 Dev and FLUX.2 Dev offer pixel size with a schema minimum of 0, a schema maximum of 2048, and a schema default of 1024. Draw Things takes a pixel canvas and rounds each side to a multiple of 64. OpenRouter and Ollama image calls have no size field.

`genimg` does not let the caller set Wiro size. `build_run_plan` in `src/genimg/core/providers/wiro_schema.py` forces `aspectRatio` to `1:1` whenever that option exists. With a reference image it also forces `width` and `height` to `1024` when those fields are still empty. A text-only FLUX run omits width and height. Live schemas store the playground default in `defaultvalue`, and the current code reads `default`, so those schema defaults are not copied into the Run body.

The caller sets an aspect ratio and a maximum extent. The maximum extent is the longer side in pixels, from 1024 through 2048. Each provider maps that pair onto the controls that provider actually has. The mapping always produces a legal request. When the model frame is not the requested frame, genimg resizes the returned image so the saved image matches the request. An omitted pair leaves each provider on its current default.

## Requirements

### Functional Requirements

- The size request has two optional parts: `aspect_ratio` and `max_extent`.
- A blank string is the same as an omitted part.
- The caller sets both parts or neither. One part without the other raises `ValidationError`.
- `max_extent` is an integer from 1024 through 2048. A value outside that range raises `ValidationError`. Those bounds are named constants. They are not environment variables and they are not `Config` fields.
- `aspect_ratio` is `auto` or two positive integers separated by `:`. Any other token raises `ValidationError`.
- `genimg generate` and `genimg character` accept `--aspect-ratio` and `--max-extent`. They do not accept `--width`, `--height`, or `--resolution`.
- `generate_image()` accepts `aspect_ratio` and `max_extent` as optional arguments.
- The Gradio generate form has an Output size block under the image-model dropdown. The block contains an aspect-ratio dropdown and a max-extent number. It does not contain width, height, or resolution controls.
- The block is visible for every provider.
- The aspect choices are rebuilt when the provider or the model changes.
- The dropdown starts with **Model default**. That choice, with an empty max extent, omits the size request.
- For a Wiro model with an `aspectRatio` select, the other choices come from that schema. The visible label is the option `text`. The submitted value is the option `value`.
- For every other model, the choices are `1:1`, `5:4`, `4:5`, `4:3`, `3:4`, `3:2`, `2:3`, `16:9`, `9:16`, and `auto`.
- The max-extent input uses 1024 and 2048 as its minimum and maximum. The hint states that this number is the longer side.
- `generate_image()` checks the pair, then calls the selected provider. The provider maps the pair locally. After a successful return, `generate_image()` fits the bitmap to the request.
- A provider does not crop or scale the bitmap. The fit step is the only resize.

### Wiro pixel models

A Wiro model with `width` and `height` and no `aspectRatio` select is a pixel model.

- The adapter sets the longer side to `max_extent` and computes the shorter side from the ratio. The shorter side is the closest integer to `max_extent * minor / major`. A tie rounds away from zero.
- `auto` means `1:1`.
- The short side may be below 1024. A wide ratio stays wide.
- When a schema `minvalue` or `maxvalue` is a positive integer, the adapter scales the pair uniformly so both sides sit inside that schema range and inside 1024–2048 on the long side.
- When the schema floor and ceiling cannot both be met, the adapter sends the schema maximum on the long side and the schema minimum on the short side. The later bitmap fit restores the requested ratio.
- The Run body sends those integers. It does not send `aspectRatio` or `resolution`.
- This path does not raise `ValidationError` for a legal ratio.

### Wiro ratio models

A Wiro model with an `aspectRatio` select is a ratio model, including a model that also has `width` and `height`.

- The adapter does not send `width` or `height`.
- `auto` matches an option whose `value` is `auto`, ignoring case. If none exists, it matches an option whose `text` is `auto`. If none exists, it matches an option whose `text` is `Match Input Image`. The Run body sends that option's `value`, including an empty string.
- Any other token that equals an option `value`, ignoring case, sends that schema spelling.
- A token that matches no option uses the closest numeric option. Distance is the absolute difference between the two width/height quotients. A tie keeps the earlier option.
- When no option has a numeric ratio, the adapter sends `defaultvalue` when that value is non-empty. Otherwise it sends the first option `value`.
- When the matched aspect option's `text` lists frames such as `2k: 2560x1440` or `(1K)1376x768`, the adapter reads each tier and its pixel pair. It sends the `resolution` value whose long side is closest to `max_extent`. A tie prefers the long side that does not exceed `max_extent`.
- When the text lists no frames, a `resolution` value that matches `<number>k` has a nominal long side of that number times 1024. The same closest-side rule applies.
- When no tier can be read, the adapter omits `resolution`.
- This path does not raise `ValidationError` because a tier is larger than `max_extent` or a short side is below 1024.

### Draw Things

- The Draw Things adapter computes the same ideal width and height as a Wiro pixel model.
- It then rounds each side with `round_dimension_to_multiple_of_64`. The grid is 64 pixels and the minimum side is 64.
- That rounded pair replaces the preset width and height for this run only.
- An omitted size request leaves the preset and the Draw Things environment variables unchanged.

### OpenRouter and Ollama

- These providers add no size field to their requests.
- Their local adapter leaves the provider payload unchanged.
- The shared bitmap fit still runs when the caller set the pair.

### Bitmap fit

- The fit runs only when the caller set both parts and the provider returned an image.
- For `auto`, the fit scales the image so its longer side equals `max_extent`. It does not crop.
- For any other ratio, the fit center-crops to that ratio, then scales so the longer side equals `max_extent`.
- Scaling uses Lanczos.
- The short side of the saved image may be below 1024.
- The fit does not read a model schema.

### Omitted request

- When the caller omits the pair, no bitmap fit runs.
- Wiro still stops forcing `aspectRatio` to `1:1` and stops forcing reference `width` and `height` to `1024`.
- When a Wiro size field's `defaultvalue` is a non-empty string, the Run body includes it.
- When `defaultvalue` is missing or blank, the Run body omits that key.
- A pixel `defaultvalue` outside the schema range is omitted. Genimg does not invent a replacement on the omitted path.

### Technical Constraints

- Size is per run. This feature adds no environment variable and no `Config` field.
- Existing Draw Things variables such as `GENIMG_DRAW_THINGS_WIDTH_PX` stay as they are. They apply only when the caller omits the size pair.
- Click options for the new flags do not set `envvar`.
- The caller does not send `resolution`, `width`, or `height`. A provider adapter may write those fields.
- Wiro reads schema ids `aspectRatio`, `resolution`, `width`, and `height` only.
- Wiro reads `defaultvalue` for those four ids only. `_static_schema_fields` continues to read `default` for every other parameter.
- Option objects use `value` and `text`, matching live Tool/Detail payloads.
- JSON and multipart Wiro Run bodies both go through `build_run_plan`.
- The web UI reuses the existing Wiro Tool/Detail cache. It does not add a second cache.
- New `generate()` arguments are keyword-only and default to `None`, so current callers stay valid.
- New Gradio handler arguments are appended and default to empty, so current unit tests that call the handlers stay valid.
- Reference-image padding stays unchanged. `process_reference_image` still pads to `Config.aspect_ratio`, whose code default is 1:1.
- Lint and tests use the project venv: `.venv/bin/ruff`, `.venv/bin/mypy`, and `.venv/bin/pytest`.

### Edge Cases & Error Handling

- `--aspect-ratio ""` and a blank library string are omitted values.
- `--aspect-ratio 16:9` without `--max-extent`, and `--max-extent 2048` without `--aspect-ratio`, raise `ValidationError` before a provider runs.
- `--max-extent 1023` and `--max-extent 2049` raise `ValidationError`.
- `7:5` is a legal ratio. A Wiro ratio model snaps it to the closest schema option. The bitmap fit then center-crops to `7:5`.
- On FLUX, `16:9` at extent 1024 sends a wide pair whose short side is below 1024. The saved image is 1024×576.
- On FLUX, `1:1` at extent 2048 sends 2048×2048. The saved image is 2048×2048.
- A ratio model whose `16:9` frames are 2560 and 3840 on the long side selects the 2560 tier at extent 2048. The bitmap fit scales that result to a long side of 2048.
- A ratio model whose `1:1` frames are 1920 and 2880 selects the 1920 tier at extent 2048, because 1920 is closer than 2880 and it does not exceed the extent. The bitmap fit scales the square up to 2048.
- `auto` on a ratio model selects the auto option and does not crop the result. The fit only sets the long side.
- `auto` on FLUX and Draw Things requests a square canvas. The fit only sets the long side.
- Draw Things `16:9` at extent 2048 requests a 64-pixel grid near 2048×1152. The fit corrects the saved image to 2048×1152.
- OpenRouter and Ollama send no size field. The saved image still has the requested ratio and long side.
- An unknown aspect token such as `wide` raises `ValidationError`.
- A Wiro model with no size fields still runs. The bitmap fit produces the requested frame.
- Schema text that says a field is required for text-to-image does not override `required: false` or a blank `defaultvalue`.
- A custom Wiro model id that Tool/Detail cannot load uses the fixed aspect list in the form. Generation uses the existing Wiro error path.
- `genimg character` merges several references into one strip before generation. This feature does not change that merge.
- The Gradio block stays visible when a schema fetch fails. Aspect choices fall back to the fixed list. The status line shows the fetch error.

## Technical Approach

### Implementation Strategy

Keep one size pair at the CLI, library, and Gradio boundary. Keep the meaning of that pair in `generate_image()`: validate it, pass it to the provider, then fit the returned bitmap.

Put the API mapping in the provider that owns the model.

- Wiro selects the pixel adapter or the ratio adapter from that model's schema inside `build_run_plan`.
- Draw Things computes a canvas and snaps it to the 64-pixel grid inside its provider.
- OpenRouter and Ollama leave their payloads unchanged.

Replace `_apply_output_sizing`. Delete `WIRO_DEFAULT_ASPECT_RATIO` and `WIRO_REFERENCE_SQUARE_SIZE`.

The bitmap fit is one function. `generate_image()` calls it. Providers do not call it.

The Gradio helper asks the active provider, or the Wiro schema cache, for the aspect choices. A failed Wiro schema load uses the fixed list.

### Affected Components

- `src/genimg/core/providers/wiro_schema.py`: replace the square-size pin. Add the pixel adapter, the ratio adapter, and the frame parser.
- `src/genimg/core/providers/wiro.py`: pass the size pair into `build_run_plan`.
- `src/genimg/core/providers/draw_things/provider.py`: map the pair to a rounded canvas for that run.
- `src/genimg/core/providers/openrouter.py` and `ollama.py`: accept the pair and leave the payload unchanged.
- `src/genimg/core/providers/base.py`: add the two keyword-only arguments to `ImageGenerationProvider.generate`.
- `src/genimg/contrib/draw_things_poc/provider.py`: accept the same arguments. Map them the same way as the main Draw Things provider.
- `src/genimg/core/image_gen.py`: validate the pair, pass it through, and fit the bitmap.
- `src/genimg/cli/commands.py`: add `--aspect-ratio` and `--max-extent` to `generate` and `character`.
- `src/genimg/ui/gradio_app.py`: add the Output size block and pass the values through `_generate_click_handler`, `_run_generate_stream`, and `_run_generate`.
- `tests/unit/test_wiro_schema.py`: replace the tests that expect a forced `1:1` or a reference-only `1024`. Cover closest-tier selection and pixel computation.
- Tests for the bitmap fit, the Draw Things canvas snap, and the CLI flags.
- `tests/unit/test_gradio_app.py`: cover the new arguments. Existing positional calls must keep working.
- `README.md`: document the two flags and the per-provider behavior.
- `docs/CHANGELOG.md`: replace the unreleased note that says Wiro text-to-image defaults `aspectRatio` to `1:1`.

No database, config schema, or environment example changes.

### Dependencies & Integration

- Wiro Tool/Detail remains the source of allowed ratios and published frames. The UI load uses `WiroClient.get_model_detail` through the provider cache.
- Draw Things keeps `round_dimension_to_multiple_of_64` from `config_builder.py`.
- The public library surface is `generate_image()`. This feature does not add a new exported type.
- Reference processing and prompt optimization stay on their current paths.

## Acceptance Criteria

- [ ] A call with no size arguments does not fit the bitmap and does not force Wiro `aspectRatio` to `1:1`.
- [ ] A Wiro reference run does not force `width` and `height` to `1024` unless that is the schema `defaultvalue` or the pixel adapter computed those pixels.
- [ ] FLUX `1:1` at extent 2048 sends 2048×2048. The saved image is 2048×2048.
- [ ] FLUX `16:9` at extent 1024 sends a wide pair and the saved image is 1024×576.
- [ ] A Wiro `16:9` model whose published long sides are 2560 and 3840 sends the 2560 tier at extent 2048. The saved image has a long side of 2048 and a `16:9` ratio.
- [ ] A requested ratio that is not a schema option still returns an image. The saved image has that ratio and that long side.
- [ ] Extent 1023, extent 2049, a partial pair, and a non-ratio token raise `ValidationError` before a provider runs.
- [ ] Draw Things receives a 64-pixel canvas for the pair. The saved image matches the requested ratio and long side.
- [ ] OpenRouter and Ollama payloads gain no size field. The saved image matches the requested ratio and long side.
- [ ] `auto` does not center-crop. It sets the long side to `max_extent`.
- [ ] The Gradio block shows aspect ratio and max extent for every provider.
- [ ] Wiro schema choices replace the fixed list when the schema loads. A failed load keeps the fixed list.
- [ ] No new environment variable or `Config` field exists for this feature.
- [ ] `.venv/bin/ruff check src/ tests/`, `.venv/bin/mypy src/`, and `.venv/bin/pytest tests/unit/` pass.

## Implementation Tasks

- [ ] Validate the size pair in `generate_image()` and fit the returned bitmap there.
- [ ] Replace `_apply_output_sizing` with the Wiro pixel adapter and the Wiro ratio adapter.
- [ ] Map the pair to a Draw Things canvas with the existing 64-pixel rounding.
- [ ] Accept the pair on OpenRouter, Ollama, and the contrib Draw Things provider.
- [ ] Add `--aspect-ratio` and `--max-extent` to `generate` and `character` with no `envvar`.
- [ ] Add the Gradio Output size block for every provider.
- [ ] Update unit tests for schema defaults, pixel math, closest-tier fallback, bitmap fit, and CLI flags.
- [ ] Update `README.md` and the unreleased `docs/CHANGELOG.md` entry.

## Risk Assessment

### Potential Issues

- Current Wiro runs that relied on the forced square image will follow the schema default instead. For Seedream and Nano Banana Pro that default is auto or match-input. For FLUX the explicit default becomes 1024×1024 when that `defaultvalue` is present.
- The closest published tier can be larger than `max_extent`. The bitmap fit scales it down. A tier whose ratio is not the requested ratio is center-cropped, so the model does not compose that exact frame.
- Scaling a small model frame up to 2048 softens detail. This happens when the closest tier is below the extent, such as a 1920 square scaled to 2048.
- Reference images are padded to `Config.aspect_ratio` (code default 1:1) before upload. A model auto ratio follows that padded image, not the original file ratio. `genimg character` compounds this: several photos become one strip, then the strip is padded.
- The Gradio model dropdown allows a custom id. A schema fetch on each Wiro model change calls Wiro when the cache is cold.
- Frame parsing depends on a tier token and a `widthxheight` pair in option text. Text without that shape uses the nominal `<number>k` times 1024 rule.
- `_static_schema_fields` still ignores `defaultvalue` for non-size parameters. Required fields such as `maxImages` keep today's type fallback.

### Mitigation Strategies

- Keep API mapping inside the provider that owns the model. Keep the bitmap fit in `generate_image()`.
- Document that the saved frame matches the request and that the model request is the nearest legal frame.
- Reuse the process schema cache. On fetch failure, keep the fixed aspect list and leave Generate available.
- Keep frame parsing in one function with tests for the Seedream colon form and the Nano Banana parenthesis form.
- Keep the size-field `defaultvalue` read inside the Wiro size mapper.

### Investigation Requirements

- None. Wiro schemas for the bundled model ids were read from the live model pages on 2026-10-24. Implementation must trust the schema returned at run time, not a copy of those option lists.

## Out of Scope

- An OpenRouter `image_config` field. OpenRouter has no size field in this feature.
- A change to reference-image padding or to `Config.aspect_ratio`.
- Reading `defaultvalue` for parameters other than the four Wiro size ids.
- New environment variables, config keys, or saved UI preferences.
- Caller-supplied width, height, or resolution.
- Hard-coded Wiro option lists. The fixed aspect list is only the caller-facing fallback.
- Environment or `Config` control of the 1024 and 2048 bounds.
