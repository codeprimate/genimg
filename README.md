# genimg - AI Image Generation Tool

A Python package for generating AI images with intelligent prompt optimization. Generate high-quality images from simple text descriptions using multiple AI models via OpenRouter (or local providers), with optional local prompt enhancement via the **Ollama HTTP API**.

**Current version:** 0.18.0 (see [CHANGELOG](docs/CHANGELOG.md) for recent changes).

## Features

- 🎨 **Multiple AI Models & Providers**: Generate images via **OpenRouter** (cloud), **Wiro** (cloud), **Ollama** (local), or **Draw Things** (local gRPC on macOS). Choose provider and model in the UI or config.
- ✨ **Prompt Optimization**: Automatically enhance prompts using local Ollama over **HTTP** (same `OLLAMA_BASE_URL` as Ollama image generation); optional in both CLI and web UI
- 🖼️ **Reference Images**: Use reference images to guide style/generation (OpenRouter, Wiro, and Draw Things); process refs for optimization context (all providers). CLI and web UI.
- 📐 **Output size**: Set aspect ratio and max extent together on the CLI, in `generate_image()`, and in the web UI. The longer side is 1024 through 2048. The saved image matches that request.
- 📑 **Character turnaround (CLI)**: `genimg character` builds a turnaround-style sheet from one or more reference images (base prompt in bundled `prompts.yaml` under `character.template`, plus optional `--prompt` / `-p`).
- 📷 **Reference Image Description**: In the web UI, describe a reference image (prose or tags via Florence/JoyTag) and optionally feed that into prompt optimization
- 💻 **Dual Interface**: Both CLI and web UI (Gradio) interfaces
- 🔔 **Browser Notifications**: Web UI can notify when generation or optimization completes (optional; permission on first load)
- 🎭 **Rich CLI**: Beautiful progress displays with spinners, progress bars, and formatted results; cancellation via Ctrl+C
- 📦 **Library Usage**: Use as a Python library with `generate_image`, `optimize_prompt`, `Config`, and configurable logging
- 🔧 **Type-Safe**: Full type hints for better IDE support
- 📝 **Structured Logging**: Default stderr is quiet for routine logs (WARNING+); `-v` for activity and prompts, `-vv` for API/cache detail; `GENIMG_VERBOSITY` and `set_verbosity()` for library/UI
- 🔑 **API Key Override**: Pass `--api-key` to CLI (`generate`, `character`, or `ui`) to override environment without editing `.env`
- 💾 **Save Optimized Prompt**: Use `--save-prompt <path>` to write the optimized prompt to a file for reproducibility

## Installation

### Prerequisites

- Python 3.10 or higher
- **OpenRouter API key** ([get one here](https://openrouter.ai/keys)) — required for cloud image generation via OpenRouter. Not needed if you use only Ollama, Draw Things, or Wiro.
- **Wiro API credentials** ([wiro.ai panel](https://wiro.ai/panel/project)) — required when using Wiro as the image provider (`WIRO_API_KEY`, `WIRO_API_SECRET`).
- **Ollama** ([install here](https://ollama.ai)) — optional for prompt optimization; required if you use Ollama as the image provider.

### Install from GitHub

**Note:** This package is not yet published to PyPI. You can install it directly from GitHub or from a local clone.

#### Option 1: Install directly from GitHub (recommended)

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install from GitHub
pip install git+https://github.com/codeprimate/genimg.git
```

#### Option 2: Install from local clone

```bash
# Clone the repository
git clone https://github.com/codeprimate/genimg.git
cd genimg

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package
pip install -e .

# Install development dependencies (optional, for contributors)
pip install -r requirements-dev.txt
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Required (for OpenRouter image generation)
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Optional overrides (defaults live in src/genimg/models.yaml)
# GENIMG_DEFAULT_MODEL=...
# GENIMG_DEFAULT_OLLAMA_IMAGE_MODEL=...
# GENIMG_DEFAULT_IMAGE_PROVIDER=openrouter   # or "ollama", "draw_things", or "wiro"
# GENIMG_DRAW_THINGS_DEFAULT_MODEL=moodymix_zitv10dpo_f16.ckpt
# WIRO_API_KEY=...                         # when provider is wiro
# WIRO_API_SECRET=...                      # signature auth for Wiro Run
# GENIMG_DEFAULT_WIRO_IMAGE_MODEL=bytedance/seedream-v4-5-uncensored
# GENIMG_OPTIMIZATION_MODEL=...
GENIMG_VERBOSITY=0                        # 0=quiet (WARNING+), 1=INFO+prompts, 2=DEBUG (CLI/UI/library)
```

Or set environment variables directly:

```bash
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
```

See [DEVELOPMENT.md](docs/DEVELOPMENT.md) and `.env.example` for all options (UI port/host/share, Ollama base URL, etc.).

### CLI API Key Override

You can provide or override the API key via the command line:

```bash
# Provide API key directly (useful when environment variable is not set)
genimg generate "a sunset" --api-key sk-or-v1-your-key-here

# Override environment variable for a single run
genimg generate "a sunset" --api-key sk-or-v1-different-key

# Works with character and ui too
genimg character "My Hero" ref.jpg --api-key sk-or-v1-your-key-here
genimg ui --api-key sk-or-v1-your-key-here
```

This is useful for:
- Running without setting environment variables
- Using different API keys for different projects
- Automated scripts where keys come from secure vaults
- Testing with different accounts

## Usage

### Web Interface (Gradio)

Launch the web UI:

```bash
genimg-ui
```

Or use the CLI subcommand (e.g. to set port or share):

```bash
genimg ui
genimg ui --port 8080
genimg ui --host 0.0.0.0   # Listen on all interfaces (LAN)
genimg ui --share          # Create a public gradio.live link
```

Then open your browser to the displayed URL (default: http://127.0.0.1:7860).

The web UI supports:

- **Prompt & optimization**: Main prompt, optional enhancement (checkbox), and an editable optimized-prompt box. Use **Enhance Prompt** to run optimization, or **Generate** with optimization on to optimize then generate in one go.
- **Reference image**: Upload a reference image. It is sent only when the selected provider supports references (OpenRouter, Wiro, and Draw Things). With **Ollama** it is used only as optimization context (not sent to the image model). Optional **Describe** (prose or tags) and **Use image description** feed description text into optimization.
- **Provider & models**: Choose image provider (**OpenRouter**, **Wiro**, **Ollama**, or **Draw Things**) and pick image/optimization models from dropdowns.
- **Output size**: Set aspect ratio and max extent together, or leave both at the model default. Max extent is 1024 through 2048. Wiro shows schema ratios when the model has them. The saved image matches the request.
- **Generation**: **Generate** with progress, **Stop** to cancel, then view or download the result (JPG, timestamped filename).
- **Browser notifications**: Optional alerts when generation or optimization completes (permission on first load; useful if the tab is in the background).
- **Edits preserved**: Changes to the optimized prompt made while generation is running are kept when the run finishes.

The app uses a package logo and favicon when available.

**UI environment variables:**

- `GENIMG_UI_PORT` — Port for the server (default: 7860).
- `GENIMG_UI_HOST` — Host to bind (default: 127.0.0.1). Use `0.0.0.0` for LAN access.
- `GENIMG_UI_SHARE` — Set to `1` or `true` to create a public share link.

### Command Line Interface

The CLI provides rich, informative progress displays with spinners, progress bars, and formatted results:

```bash
genimg generate "a red sports car at sunset" --output car.png
```

**Example output:**
```
⠋ Optimizing prompt (huihui_ai/qwen3.5-abliterated:4b) 2.3s
⠙ Generating image (bytedance-seed/seedream-4.5) • optimized 12.1s

╭──────────────────────────── ✓ Image Generated ───────────────────────────────╮
│                                                                              │
│   Saved to  car.png                                                          │
│      Model  bytedance-seed/seedream-4.5                                      │
│       Time  15.3s                                                            │
│   Features  ✓ Optimized                                                      │
│      Input  a red sports car at sunset                                       │
│  Optimized  A sleek red sports car photographed during golden hour, shot     │
│             with 85mm lens creating shallow depth of field, parked on        │
│             coastal highway with ocean backdrop, cinematic lighting with     │
│             warm sunset tones, professional automotive photography style     │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
car.png
```

**Skip optimization** (generates immediately):

```bash
genimg generate "a red sports car" --no-optimize --output car.png
```

**With a reference image:**

```bash
genimg generate "same car but in blue" --reference original.jpg --output blue_car.png
```

**Output size** (pass both flags, or neither):

```bash
genimg generate "a red sports car" --aspect-ratio 16:9 --max-extent 1024 --no-optimize --output car.png
genimg character "Rogue Pilot" ref.jpg --aspect-ratio 1:1 --max-extent 2048
```

`--aspect-ratio` is `auto` or a ratio such as `16:9`. `--max-extent` is the longer side in pixels, from 1024 through 2048. Omit both flags to keep the model default.

- Wiro maps the pair to schema aspect options or to width and height. The model request is the nearest legal frame.
- Draw Things snaps each side to a multiple of 64. `GENIMG_DRAW_THINGS_WIDTH_PX` and `GENIMG_DRAW_THINGS_HEIGHT_PX` apply only when the pair is omitted.
- OpenRouter and Ollama have no size field. The saved image is still fitted to the request.
- Reference image padding still uses `Config.aspect_ratio`.

**Save optimized prompt for reproducibility:**

```bash
genimg generate "a red car" --output car.png --save-prompt prompts/car.txt
```

This saves the optimized prompt to a file, allowing you to:
- Reproduce exact generation conditions later
- Learn from optimization patterns
- Version control your prompts
- Use in automated workflows

**Quiet mode** (machine-readable output, no progress):

```bash
genimg generate "a landscape" --output out.png --quiet
# Output: out.png
```

**Verbosity and logging:**

- Default (`GENIMG_VERBOSITY=0` or unset): the `genimg` logger is at **WARNING** — routine INFO lines (e.g. "Generating image") are not shown; warnings and errors still appear.
- `-v` / `GENIMG_VERBOSITY=1`: **INFO** — activity and performance, plus prompt text where applicable.
- `-vv` / `GENIMG_VERBOSITY=2`: **DEBUG** — API calls, cache hits/misses, and other debug detail.
- CLI `-v` / `-vv` override `GENIMG_VERBOSITY` when passed.

```bash
genimg generate "a cat" --no-optimize -o out.png -v    # show prompts in logs
genimg generate "a cat" --no-optimize -o out.png -vv   # full debug logs
GENIMG_VERBOSITY=1 genimg generate "a cat" -o out.png # same as -v
```

**Character turnaround** (`genimg character`):

Uses a fixed turnaround-oriented prompt plus your reference image(s). There is no separate prompt-optimization step on this command.

- **Arguments:** a **TITLE** (default output filename is derived from it), then **one or more** image paths. Optional extra instructions for the model: `--prompt` / `-p` only (not a second positional).

```bash
genimg character "Rogue Pilot" refs/front.jpg refs/side.jpg -o sheet.png
genimg character "Rogue Pilot" ref.jpg   # timestamped file in the current directory
```

- **Defaults:** same as `genimg generate` — provider and model come from config / `models.yaml` unless you pass `--provider` / `--model`. `--aspect-ratio` and `--max-extent` work the same way as on `genimg generate`. Reference images require **OpenRouter**, **Wiro**, or **Draw Things** (not Ollama).
- **Scripting:** on success, stdout is a single line (saved path). `--quiet` suppresses stderr progress/banner. `--api-key`, `-v` / `-vv`, `GENIMG_VERBOSITY`, and `--debug-api` are supported. Prefer **OpenRouter** unless your image provider accepts the references you pass (see [Reference images with Ollama](#reference-images-with-ollama)). Full detail: `genimg character --help`.

### As a Python Library

```python
from genimg import DEFAULT_IMAGE_MODEL, generate_image, optimize_prompt, Config

# Configure
config = Config.from_env()
config.validate()

# Generate an image (default model from models.yaml / config)
result = generate_image(
    prompt="a serene mountain landscape at dawn",
    model=DEFAULT_IMAGE_MODEL,
)

# Or use Wiro for cloud image generation (owner/model slug)
result = generate_image("a cat", provider="wiro", model="bytedance/seedream-v4-5-uncensored")

# Or use Ollama for image generation
result = generate_image("a cat", provider="ollama", model="llama3.2-vision")

# Request a size. The saved image matches the pair.
# The model request is the nearest legal frame.
result = generate_image("a cat", aspect_ratio="16:9", max_extent=1024)

# Save the image (result.image is a PIL Image; result.image_data is bytes)
with open("output.png", "wb") as f:
    f.write(result.image_data)
# Or: result.image.save("output.jpg", "JPEG", quality=90)

print(f"Generated in {result.generation_time:.2f}s")

# Optimize a prompt (Ollama)
optimized = optimize_prompt("a mountain landscape")
result = generate_image(prompt=optimized)

# Reference image (OpenRouter): process_reference_image() + pass reference_image_b64
# Describe image: describe_image() from genimg.core.image_analysis
# List Ollama models: list_ollama_models()
from genimg import set_verbosity
set_verbosity(1)  # 0=WARNING, 1=INFO+prompts, 2=DEBUG; or GENIMG_VERBOSITY
```

## Prompt Optimization

Prompt optimization uses Ollama over **HTTP** (same server as image generation: `OLLAMA_BASE_URL` / `GENIMG_OLLAMA_BASE_URL`, default `http://127.0.0.1:11434`) to enhance your simple descriptions into detailed, effective prompts. The optimizer adds:

- Technical photography details (camera angles, lighting)
- Spatial relationships and scene layout
- Style and artistic qualities
- Relevant contextual details

**Example:**
- **Original**: "a red car"
- **Optimized**: "A sleek red sports car photographed at golden hour, shot with 85mm lens creating shallow depth of field, parked on coastal highway with ocean backdrop, cinematic lighting with warm sunset tones, professional automotive photography style"

## Available Models

Default model IDs are defined in [`src/genimg/models.yaml`](src/genimg/models.yaml). Override via `GENIMG_DEFAULT_MODEL`, `GENIMG_DEFAULT_OLLAMA_IMAGE_MODEL`, `GENIMG_DEFAULT_WIRO_IMAGE_MODEL`, and `GENIMG_OPTIMIZATION_MODEL`.

- **Image generation**: Default OpenRouter model from `models.yaml`. Switch provider to **Wiro**, **Ollama**, or **Draw Things** via config or UI.
- **Prompt optimization**: Uses Ollama via the HTTP API; default from `models.yaml`.

Check [OpenRouter's model list](https://openrouter.ai/models) for more cloud image models.

## Development

### Setup

```bash
# Install package in development mode with dev dependencies (recommended)
make install-dev

# Or manually: install editable + dev extras
pip install -e ".[dev]"
```

### Code Quality

```bash
# Format code
make format

# Lint code
make lint

# Type check
make typecheck

# Run all checks
make check
```

### Testing

```bash
# Run all tests (unit only; integration tests are excluded)
make test

# Run only unit tests
make test-unit

# Run with coverage
make coverage
```

**Integration tests** (optional, manual): they call real external APIs (OpenRouter, Wiro, etc.), are slow, and may cost money. They are excluded from `make test`. To run them:

```bash
GENIMG_RUN_INTEGRATION_TESTS=1 make test-integration
# Wiro only (also requires WIRO_API_KEY and --run-slow):
GENIMG_RUN_INTEGRATION_TESTS=1 .venv/bin/pytest tests/integration/test_wiro_image_gen.py --run-slow
```

Requires API credentials in `.env` or the environment (`OPENROUTER_API_KEY` and/or `WIRO_API_KEY`). Output images are written to `tmp/`. See [Development Guide](docs/DEVELOPMENT.md#integration-tests-manual-slow-costs-money) for details.

## Project Structure

```
genimg/
├── src/genimg/          # Main package
│   ├── core/            # Core business logic
│   ├── ui/              # Gradio web interface
│   ├── cli/             # Command-line interface
│   └── utils/           # Utilities
├── tests/               # Test suite
├── scripts/             # Development scripts
└── docs/                # Documentation
```

## Documentation

- [SPEC.md](docs/SPEC.md) — Product / functional specification
- [DEVELOPMENT.md](docs/DEVELOPMENT.md) — Developer guide (setup, testing, modifying UI)
- [AGENT.md](AGENT.md) — AI agent development guide
- [DECISIONS.md](docs/DECISIONS.md) — Architecture decisions
- [EXAMPLES.md](docs/EXAMPLES.md) — Usage examples
- [browser-notifications.md](docs/browser-notifications.md) — Web UI notification flow
- [CHANGELOG.md](docs/CHANGELOG.md) — Change history
- [releases/v0.18.0.md](docs/releases/v0.18.0.md) — v0.18.0 release notes (output size)
- [releases/v0.17.0.md](docs/releases/v0.17.0.md) — v0.17.0 release notes (Wiro provider)

## Troubleshooting

### "Ollama is not available"

If you see this error and want to use prompt optimization:
1. Install Ollama from https://ollama.ai and **start the Ollama app or service** so it listens for HTTP (default `http://127.0.0.1:11434`).
2. Pull a model: `ollama pull huihui_ai/qwen3.5-abliterated:4b`
3. If Ollama runs elsewhere, set **`OLLAMA_BASE_URL`** or **`GENIMG_OLLAMA_BASE_URL`** to match (same variable used for Ollama image generation).
4. Quick check: `curl -sS http://127.0.0.1:11434/api/tags` should return JSON (adjust the host if you changed the base URL).

You can generate images without Ollama by skipping optimization.

### "OpenRouter API key is required"

This appears when using OpenRouter for image generation. Set `OPENROUTER_API_KEY` in your environment or `.env`, or switch the image provider to Ollama, Wiro, or Draw Things (UI dropdown or `GENIMG_DEFAULT_IMAGE_PROVIDER`).

### "Wiro API key is required"

Set `WIRO_API_KEY` (and usually `WIRO_API_SECRET` for Run requests) when using Wiro. See `.env.example`.

### Reference images with Ollama

Reference images are sent to the image model when using **OpenRouter**, **Wiro**, or **Draw Things**. With **Ollama**, the reference is used only as context for prompt optimization (e.g. with "Use image description"); the image is not sent to the Ollama image model.

### Image Processing Errors

For HEIC/HEIF images, ensure `pillow-heif` is installed:
```bash
pip install pillow-heif
```

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please read [DEVELOPMENT.md](docs/DEVELOPMENT.md) for guidelines.

## Support

- Issues: [GitHub Issues](https://github.com/codeprimate/genimg/issues)
- Discussions: [GitHub Discussions](https://github.com/codeprimate/genimg/discussions)
