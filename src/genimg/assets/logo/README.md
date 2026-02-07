# Logo assets

Source: `docs/samples/logos/logo_final.png`

Generated sizes (PNG): 16, 32, 48, 64, 128, 256, 512.

- **favicon.ico** — Multi-resolution (16, 32, 48, 64, 128, 256) for browser tabs and bookmarks.
- **logo_N.png** — Square logo at N×N pixels for UI (e.g. header), docs, or app icons.

Used by the Gradio UI (favicon and optional header logo). Regenerate from source with ImageMagick:

```bash
SRC=docs/samples/logos/logo_final.png
DST=src/genimg/assets/logo
for s in 16 32 48 64 128 256 512; do magick "$SRC" -resize ${s}x${s} "$DST/logo_${s}.png"; done
magick "$SRC" -define icon:auto-resize=256,128,64,48,32,16 "$DST/favicon.ico"
```
