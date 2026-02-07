# Gradio UI Plan (Final)

**Status:** Final — ready for implementation.  
**Aligns with:** SPEC.md, LIBRARY_SPEC.md, CLI_PLAN.md, ADR-007 (Gradio), ADR-009 (Python 3.10 + Gradio 6), ADR-010 (GenerationResult returns PIL Image).

---

## 1. Python and Gradio version

- **Python:** >=3.10 (required by Gradio 6).
- **Gradio:** 6.x (e.g. `>=6.0.0,<7`). Use [Gradio 6 docs](https://www.gradio.app/docs/) and [Blocks and event listeners](https://www.gradio.app/guides/blocks-and-event-listeners) for all implementation.
- **Consequence:** No Gradio 4–specific behavior; follow current Gradio 6 APIs for layout, events, and cancellation.

---

## 2. Scope constraints (locked)

| Area | Constraint |
|------|------------|
| **Output / download** | Use the image component’s **built-in download** only. No separate Save button. |
| **Download filename** | Integer timestamp only (e.g. `int(time.time())`). Example: `1739123456.jpg`. |
| **Download format** | **JPG, quality 90.** The library returns a PIL Image (`result.image`); the UI converts to bytes for the download via `result.image.save(io.BytesIO(), "JPEG", quality=90).getvalue()` and uses the timestamp for the filename. |
| **Reference image** | **Drag-and-drop** using the **standard Gradio Image** component (default upload + drag-and-drop). No custom widget. |
| **Output** | **Single image** only. No gallery, no history. One result at a time; new run replaces the displayed image. |
| **Saving** | No “Save to folder” or file picker. Saving = user uses the component’s download only. |
| **Prompt** | Single **multiline textbox**. No templates or presets in scope. |
| **Model** | Image model: from config or one dropdown. Optimization model: from config/env only (no UI in v1). |
| **Optimized prompt** | **Editable** textbox. User can edit the optimized prompt then click Generate (SPEC: review and edit before proceeding). |
| **Regenerate prompt** | **Optimize** button runs optimization only and fills the Optimized prompt box; clicking again = regenerate (SPEC: regenerate optimized prompt if not satisfied). |

---

## 3. Goals

- Web UI for the same flow as the CLI: prompt → optional optimize → optional reference → generate → view/download.
- **Edit then generate:** User can run Optimize (or Generate with optimize on), see the optimized prompt in an editable box, edit it, then click Generate to use that text.
- **Regenerate optimized prompt:** Optimize button runs optimization only; clicking it again runs optimization again (regenerate).
- Launch via `genimg-ui` (and optionally `genimg ui`).
- Clear path from “I have an idea” to “I have an image,” with progress, cancellation, and clear errors.

---

## 4. Layout (single-page, vertical)

1. **Title** — Short description: “AI image generation with optional prompt optimization.”
2. **Prompt + actions**
   - **Prompt:** `gr.Textbox` (multiline, placeholder, required).
   - **Generate** button (primary).
   - **Stop** button (enabled only while running).
3. **Options**
   - **Optimize prompt:** `gr.Checkbox` (default True), label e.g. “Optimize prompt with AI (Ollama).”
   - **Reference image:** `gr.Image` (standard upload + drag-and-drop).
   - **Model:** `gr.Dropdown` (optional, from config).
4. **Optimized prompt** — `gr.Textbox` (editable, multiline). Filled by Optimize button or when Generate runs with optimize on. User can edit then click Generate.
5. **Optimize** button — Runs optimization only; fills Optimized prompt box. Click again = regenerate.
6. **Status** — Read-only text: “Optimizing…”, “Generating…”, “Done in X.Xs”, or error message.
7. **Output** — `gr.Image` for the result (built-in download).

---

## 5. State machine and button states

**States:** idle → optimizing (Optimize button or Generate with optimize on) or generating → done | error | cancelled.

| State | Generate | Optimize | Stop |
|-------|----------|----------|------|
| idle | Enabled if prompt non-empty | Enabled if prompt non-empty | Disabled |
| optimizing / generating | Disabled | Disabled | Enabled |
| done / error / cancelled | Enabled | Enabled | Disabled |

**Transitions:** idle → optimizing on Optimize (optimize-only) or on Generate (if optimize on and box empty); optimizing → generating (Generate flow) or done (Optimize flow) or cancelled or error; generating → done or cancelled or error; done/error/cancelled → idle. Empty prompt: Generate and Optimize disabled (inline validation).

---

## 6. Generate/cancel flows (all cases)

| # | Flow | Resulting state |
|---|------|-----------------|
| 1 | Happy path (optimize on): validate → optimize → generate → success | done |
| 2 | Happy path (no optimize): validate → generate → success | done |
| 3 | Cancel during optimization (Stop → cancel_check True → CancellationError) | cancelled |
| 4 | Cancel during generation | cancelled |
| 5 | Error during optimization (e.g. Ollama timeout) | error |
| 6 | Error during generation (e.g. APIError) | error |
| 7 | Empty prompt | idle |
| 8 | Config invalid (e.g. missing API key) | error |
| 9 | Reference image invalid (ImageProcessingError) | error |

Handler catches `CancellationError` and returns status “Cancelled.” and restores button states; no new image.

---

## 7. Prompt optimization (in context)

- **Generate logic:** If **Optimized prompt** box has content → use it as `effective_prompt` (edit-then-generate; do not run optimize). Else if **Optimize prompt** checkbox on → run `optimize_prompt(...)`, fill Optimized prompt box with result, then `generate_image(effective_prompt, ...)`. Else → use **Prompt** as `effective_prompt`.
- **Optimize button:** Runs optimization only; fills Optimized prompt box. **Regenerate** = click Optimize again. Same validation and reference handling; supports cancellation via Stop.
- **Optimize on (no pre-filled box):** validate → process reference (if any) → `optimize_prompt(..., reference_hash=ref_hash, cancel_check=...)` → fill Optimized prompt box → `generate_image(effective_prompt, ...)`. States: optimizing then generating.
- **Optimize off / use Prompt:** validate → process reference (if any) → `generate_image(prompt, ...)`. State: generating only.
- **Reference:** one `process_reference_image`; pass `reference_hash` to `optimize_prompt`, `reference_image_b64` to `generate_image`.
- **Optimization model:** from config; no UI in v1.
- **Cache:** library may return cached optimized prompt; UI does not show “cached” (same status flow).

---

## 8. Library integration

- **Generate handler:** Load config, validate prompt. Process reference if provided. If optimize on: `optimize_prompt(..., cancel_check=lambda: event.is_set())`; use result as effective prompt. Call `generate_image(effective_prompt, ..., cancel_check=lambda: event.is_set())`. Library returns `GenerationResult` with **`result.image`** (PIL). Use `result.image` for display and download: e.g. `buf = io.BytesIO(); result.image.save(buf, "JPEG", quality=90); download_bytes = buf.getvalue()`; filename `f"{int(time.time())}.jpg"`. Map exceptions to user-facing messages (same as CLI).
- **Stop handler:** Set shared `threading.Event`. Optionally use Gradio 6 `cancels=[generate_event]` on the Stop button.
- **Shared event:** One `threading.Event` (e.g. module-level). Generate clears at start; Stop sets it. Pass `cancel_check=lambda: event.is_set()` to `optimize_prompt` and `generate_image`.

---

## 9. Output image (PIL from library)

- The library returns `GenerationResult` with **`image`** (PIL Image) as primary output (ADR-010).
- **Display:** Pass bytes or numpy from `result.image` to `gr.Image` in the format Gradio 6 expects (see Gradio 6 Image component docs).
- **Download:** For the component’s download, provide bytes from `result.image.save(io.BytesIO(), "JPEG", quality=90).getvalue()` and suggest filename `{int(time.time())}.jpg` (per scope constraints).

---

## 10. CLI integration

- **Entry point:** `genimg-ui` → `genimg.ui.gradio_app:launch`.
- **Optional:** `genimg ui` subcommand with `--port`, `--host`, `--share`.
- **Launch:** Build the Blocks app, then `gr.Blocks.launch(server_name="127.0.0.1", server_port=7860)` (or from env: `GENIMG_UI_PORT`, default 7860). Default bind 127.0.0.1; document `GENIMG_UI_SHARE` or `--host 0.0.0.0` for sharing/LAN.

---

## 11. File layout

- **UI code:** `src/genimg/ui/gradio_app.py` — build Gradio UI, generate handler (using only public API: `from genimg import ...`), exception mapping, cancellation event, `launch()`.

---

## 12. Implementation phases

**Phase 1 — Minimal UI**  
Layout (prompt, optimize checkbox, reference Image, Generate, status, output Image). Generate handler: validate config and prompt, process reference, optional optimize, `generate_image`, then use `result.image` to produce display + download (JPG 90, timestamp filename). Exception → user message. Replace stub `launch()` with real `gr.Blocks.launch(...)`. No cancellation yet.

**Phase 2 — Cancellation and polish**  
Shared `threading.Event`, Stop button, `cancel_check` passed to `optimize_prompt` and `generate_image`. On `CancellationError`, return “Cancelled.” and restore button states. Button enable/disable per state. Optional: model dropdown, show optimized prompt in read-only box.

**Phase 3 — Optional**  
`genimg ui` subcommand; document `GENIMG_UI_PORT`, `GENIMG_UI_SHARE` in README/DEVELOPMENT.

---

## 13. Testing

- **Unit:** Mock library calls in the generate handler; assert optimize/generate (or not), reference passed, image/output and exception mapping.
- **Manual:** Run `genimg-ui`, full flow and cancel flow.

---

## 14. Decisions (final)

| Topic | Decision |
|-------|----------|
| Server default | 127.0.0.1; document 0.0.0.0 / share for LAN. |
| Optimize-only in UI | Deferred; not in v1. |
| Model / optimization-model UI | Image model: one dropdown from config; optimization model: config/env only. |
| `genimg ui` subcommand | Add for consistency and `genimg ui --port X`. |

---

## 15. Summary

- **Stack:** Python 3.10+, Gradio 6.x, public API only, `result.image` (PIL) for display and download.
- **Scope:** Single image, built-in download, JPG quality 90, timestamp filename, reference = standard Image drag-and-drop, no gallery/save-to-folder.
- **Flow:** State machine and all nine generate/cancel flows defined; button states and library interrupt (Event + cancel_check) specified.
- **Phases:** (1) minimal UI + launch, (2) cancellation + button states, (3) optional CLI subcommand and docs.

This plan is final and ready for implementation.
