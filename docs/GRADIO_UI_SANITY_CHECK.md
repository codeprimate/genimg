# Gradio UI — Scope & Flow Sanity Check

**Reference:** GRADIO_UI_PLAN.md (final).

---

## Scope constraints (plan §2) — ✅ Met

| Constraint | Implementation |
|------------|----------------|
| Output / download | Built-in only; no separate Save button. ✅ |
| Download filename | `int(time.time())` → `{ts}.jpg`. ✅ |
| Download format | JPG, quality 90 via `result.image.save(..., "JPEG", quality=90)`. ✅ |
| Reference image | Standard `gr.Image` with upload + clipboard (drag-and-drop via upload). ✅ |
| Single image | One output image; new run replaces it. ✅ |
| No “Save to folder” | Saving only via component download. ✅ |
| Prompt | Single multiline `gr.Textbox`. ✅ |
| Model | From config (dropdown present but hidden/empty; optional per plan). ✅ |

---

## Layout (plan §4) — ✅ Met

- Title / short description. ✅
- Prompt (multiline, placeholder). ✅
- Generate (primary), Stop (enabled only while running). ✅
- Optimize checkbox (default True), Reference Image, Model dropdown (optional, hidden). ✅
- Status read-only, Output `gr.Image`. ✅

---

## State machine & button states (plan §5) — ✅ Met

- **Idle:** Generate enabled only when prompt non-empty; Stop disabled. ✅
- **Optimizing / generating:** Generate disabled, Stop enabled. ✅
- **Done / error / cancelled:** Generate enabled, Stop disabled. ✅
- Empty prompt: no run; message “Enter a prompt to generate.”; Generate disabled. ✅

---

## Generate/cancel flows (plan §6) — ✅ Met

| # | Flow | Handled |
|---|------|--------|
| 1 | Happy path (optimize on) | validate → optimize → generate → “Done in X.Xs”. ✅ |
| 2 | Happy path (no optimize) | validate → generate → “Done in X.Xs”. ✅ |
| 3–4 | Cancel during optimize / generate | Stop sets `_cancel_event`; `cancel_check` in library; `CancellationError` → “Cancelled.”, buttons restored. ✅ |
| 5–6 | Error during optimize / generation | Exceptions mapped via `_exception_to_message`; status shows message; buttons restored. ✅ |
| 7 | Empty prompt | Early return + message; no library calls. ✅ |
| 8 | Config invalid | `ConfigurationError` → user message. ✅ |
| 9 | Reference invalid | `ImageProcessingError` / `ValidationError` / `FileNotFoundError` → user message. ✅ |

---

## Library integration (plan §7–8) — ✅ Met

- Order: validate → process reference → optional `optimize_prompt(reference_hash=..., cancel_check=...)` → `generate_image(effective_prompt, reference_image_b64=..., cancel_check=...)`. ✅
- Shared `threading.Event`; cleared at start of generate; Stop sets it; `cancel_check=lambda: _cancel_event.is_set()` passed to both library calls. ✅
- `result.image` (PIL) used for display and download (saved as JPG 90, timestamp filename). ✅
- Stop button uses `cancels=[gen_ev]`. ✅

---

## Functionally missing or deferred (in scope)

1. **Status progression when optimize is on**  
   Plan §4: status should show “Optimizing…”, then “Generating…”, then “Done in X.Xs”.  
   **Before fix:** Only one in-progress message was shown (“Optimizing…” or “Generating…”); when optimize was on, it stayed “Optimizing…” until “Done”.  
   **Fix:** Refactor so the handler yields “Optimizing…” then “Generating…” (when optimize on) then “Done in X.Xs” (see code change below).

2. **Model dropdown**  
   Plan: “Image model: from config or one dropdown” (optional). Dropdown exists but is hidden and has no choices; model is taken from config. Acceptable as “optional”; can be populated later (e.g. from env list).

3. **Temp file accumulation**  
   Each successful run writes a new file under `tempfile.gettempdir()`. No cleanup; acceptable per plan; optional improvement for later.

---

## Out of scope (per plan)

- Optimize-only (no image). Deferred.
- Optimization model in UI. Config/env only.
- Gallery, history, “Save to folder”, templates/presets.

---

## Summary

- All nine generate/cancel flows are covered; state machine and button states match the plan; scope constraints and library integration are satisfied.
- One in-scope UX gap was the missing “Generating…” step when optimize is on; that is fixed by yielding that status between optimize and generate.
