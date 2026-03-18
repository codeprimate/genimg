# genimg - AI Image Generation Tool

A Python package for generating AI images with intelligent prompt optimization. Generate high-quality images from simple text descriptions using multiple AI models via OpenRouter, with optional local prompt enhancement via Ollama.

**Current version:** 0.10.x (see [CHANGELOG](docs/CHANGELOG.md) for recent changes).

## Features

- 🎨 **Multiple AI Models & Providers**: Generate images via **OpenRouter** (cloud) or **Ollama** (local). Choose provider and model in the UI or config.
- ✨ **Prompt Optimization**: Automatically enhance prompts using local Ollama models; optional in both CLI and web UI
- 🖼️ **Reference Images**: Use reference images to guide style/generation (OpenRouter); process refs for optimization context (both providers). CLI and web UI.
- 📷 **Reference Image Description**: In the web UI, describe a reference image (prose or tags via Florence/JoyTag) and optionally feed that into prompt optimization
- 💻 **Dual Interface**: Both CLI and web UI (Gradio) interfaces
- 🔔 **Browser Notifications**: Web UI can notify when generation or optimization completes (optional; permission on first load)
- 🎭 **Rich CLI**: Beautiful progress displays with spinners, progress bars, and formatted results; cancellation via Ctrl+C
- 📦 **Library Usage**: Use as a Python library with `generate_image`, `optimize_prompt`, `Config`, and configurable logging
- 🔧 **Type-Safe**: Full type hints for better IDE support
- 📝 **Structured Logging**: Default activity/performance logs; `-v` for prompts, `-vv` for API/cache detail; `GENIMG_VERBOSITY` and `set_verbosity()` for library/UI
- 🔑 **API Key Override**: Pass `--api-key` to CLI (generate or ui) to override environment without editing `.env`
- 💾 **Save Optimized Prompt**: Use `--save-prompt <path>` to write the optimized prompt to a file for reproducibility

## Installation

### Prerequisites

- Python 3.10 or higher
- **OpenRouter API key** ([get one here](https://openrouter.ai/keys)) — required for cloud image generation. Not needed if you use only Ollama for image generation.
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

# Optional
GENIMG_DEFAULT_MODEL=bytedance-seed/seedream-4.5
GENIMG_DEFAULT_IMAGE_PROVIDER=openrouter   # or "ollama" for local image generation
GENIMG_OPTIMIZATION_MODEL=huihui_ai/qwen3.5-abliterated:4b
GENIMG_VERBOSITY=0                        # 0=default, 1=+prompts, 2=+API/cache (CLI/UI/library)
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

# Works with the UI command too
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
- **Reference image**: Upload a reference image. With **OpenRouter** as image provider it is sent for style/guidance; with **Ollama** it is used only as context for optimization (reference not sent to the image model). Optional **Describe** (prose or tags) and **Use image description** to feed the description into optimization.
- **Provider & models**: Choose image provider (**OpenRouter** or **Ollama**) and pick image/optimization models from dropdowns (package config and installed Ollama models).
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

- Default: activity and performance are logged (e.g. "Generating image", "Generated in X.Xs").
- `-v` (info): also log prompt text (original and optimized).
- `-vv` (verbose): also log API calls, cache hits/misses, and other debug detail.
- Set `GENIMG_VERBOSITY=0` (default), `1`, or `2` in the environment to control logging when no `-v` flag is passed; CLI flags override the env var.

```bash
genimg generate "a cat" --no-optimize -o out.png -v    # show prompts in logs
genimg generate "a cat" --no-optimize -o out.png -vv   # full debug logs
GENIMG_VERBOSITY=1 genimg generate "a cat" -o out.png # same as -v
```

### As a Python Library

```python
from genimg import generate_image, optimize_prompt, Config

# Configure
config = Config.from_env()
config.validate()

# Generate an image (default: OpenRouter)
result = generate_image(
    prompt="a serene mountain landscape at dawn",
    model="bytedance-seed/seedream-4.5"
)

# Or use Ollama for image generation
result = generate_image("a cat", provider="ollama", model="llama3.2-vision")

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
set_verbosity(1)  # 0=default, 1=+prompts, 2=+API/cache; or GENIMG_VERBOSITY
```

## Prompt Optimization

Prompt optimization uses Ollama to enhance your simple descriptions into detailed, effective prompts. The optimizer adds:

- Technical photography details (camera angles, lighting)
- Spatial relationships and scene layout
- Style and artistic qualities
- Relevant contextual details

**Example:**
- **Original**: "a red car"
- **Optimized**: "A sleek red sports car photographed at golden hour, shot with 85mm lens creating shallow depth of field, parked on coastal highway with ocean backdrop, cinematic lighting with warm sunset tones, professional automotive photography style"

## Available Models

- **Image generation**: Default is OpenRouter model `bytedance-seed/seedream-4.5`. You can switch the provider to **Ollama** and use local image models (see [Ollama image models](https://ollama.com/blog/image-generation)). Set `GENIMG_DEFAULT_IMAGE_PROVIDER=ollama` or choose in the UI.
- **Prompt optimization**: Uses Ollama (default `huihui_ai/qwen3.5-abliterated:4b`). Pull the model with `ollama pull huihui_ai/qwen3.5-abliterated:4b`.

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

**Integration tests** (optional, manual): they call the real OpenRouter API, are slow, and cost money. They are excluded from `make test`. To run them:

```bash
GENIMG_RUN_INTEGRATION_TESTS=1 make test-integration
```

Requires `OPENROUTER_API_KEY` in `.env` or the environment. Output images are written to `tmp/` (timestamped filenames). See [Development Guide](docs/DEVELOPMENT.md#integration-tests-manual-slow-costs-money) for details.

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

## Troubleshooting

### "Ollama is not available"

If you see this error and want to use prompt optimization:
1. Install Ollama from https://ollama.ai
2. Pull a model: `ollama pull huihui_ai/qwen3.5-abliterated:4b`
3. Verify it works: `ollama list`

You can generate images without Ollama by skipping optimization.

### "OpenRouter API key is required"

This appears when using OpenRouter for image generation. Set `OPENROUTER_API_KEY` in your environment or `.env`, or switch the image provider to Ollama (UI dropdown or `GENIMG_DEFAULT_IMAGE_PROVIDER=ollama`) if you want to generate images locally only.

### Reference images with Ollama

Reference images are sent to the image model only when using the **OpenRouter** provider. With **Ollama**, the reference is used only as context for prompt optimization (e.g. with "Use image description"); the image is not sent to the Ollama image model.

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
