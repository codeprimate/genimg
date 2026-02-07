# genimg - AI Image Generation Tool

A Python package for generating AI images with intelligent prompt optimization. Generate high-quality images from simple text descriptions using multiple AI models via OpenRouter, with optional local prompt enhancement via Ollama.

**Current version:** 0.9.x (see [CHANGELOG](docs/CHANGELOG.md) for recent changes).

## Features

- 🎨 **Multiple AI Models**: Access various image generation models through OpenRouter (configurable in UI and CLI)
- ✨ **Prompt Optimization**: Automatically enhance prompts using local Ollama models; optional in both CLI and web UI
- 🖼️ **Reference Images**: Use reference images to guide generation (CLI and web UI)
- 💻 **Dual Interface**: Both CLI and web UI (Gradio) interfaces
- 🎭 **Rich CLI**: Beautiful progress displays with spinners, progress bars, and formatted results; cancellation via Ctrl+C
- 📦 **Library Usage**: Use as a Python library with `generate_image`, `optimize_prompt`, `Config`, and configurable logging
- 🔧 **Type-Safe**: Full type hints for better IDE support
- 📝 **Structured Logging**: Default activity/performance logs; `-v` for prompts, `-vv` for API/cache detail; `GENIMG_VERBOSITY` and `set_verbosity()` for library/UI
- 🔑 **API Key Override**: Pass `--api-key` to CLI (generate or ui) to override environment without editing `.env`
- 💾 **Save Optimized Prompt**: Use `--save-prompt <path>` to write the optimized prompt to a file for reproducibility

## Installation

### Prerequisites

- Python 3.10 or higher
- OpenRouter API key ([get one here](https://openrouter.ai/keys))
- (Optional) Ollama installed locally for prompt optimization ([install here](https://ollama.ai))

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
# Required
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Optional
GENIMG_DEFAULT_MODEL=bytedance-seed/seedream-4.5
GENIMG_OPTIMIZATION_MODEL=svjack/gpt-oss-20b-heretic
```

Or set environment variables directly:

```bash
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
```

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

The web UI supports: prompt input with optional optimization (checkbox), reference image upload, image and optimization model dropdowns (from package config and installed Ollama models), generation with progress and **Stop** to cancel, and download of the result (JPG, timestamped filename). The app uses a package logo and favicon when available.

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
⠋ Optimizing prompt (svjack/gpt-oss-20b-heretic) 2.3s
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

# Generate an image
result = generate_image(
    prompt="a serene mountain landscape at dawn",
    model="bytedance-seed/seedream-4.5"
)

# Save the image (result.image is a PIL Image; result.image_data is bytes)
with open("output.png", "wb") as f:
    f.write(result.image_data)
# Or save as JPEG with quality: result.image.save("output.jpg", "JPEG", quality=90)

print(f"Generated in {result.generation_time:.2f}s")

# Or with optimization
optimized = optimize_prompt("a mountain landscape")
print(f"Optimized prompt: {optimized}")

result = generate_image(prompt=optimized)

# Control logging verbosity (0=default activity/performance, 1=+prompts, 2=+API/cache)
from genimg import set_verbosity
set_verbosity(1)  # or set GENIMG_VERBOSITY=1 in the environment
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

The default image model is `bytedance-seed/seedream-4.5` and the default optimization model is `svjack/gpt-oss-20b-heretic`. You can use any OpenRouter-compatible image generation model. Check [OpenRouter's model list](https://openrouter.ai/models) for more options.

## Development

### Setup

```bash
# Install development dependencies
make install-dev

# Or manually
pip install -r requirements-dev.txt
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

- [SPEC.md](docs/SPEC.md) - Complete functional specification (product)
- [AGENT.md](AGENT.md) - AI agent development guide
- [DEVELOPMENT.md](docs/DEVELOPMENT.md) - Developer guide
- [DECISIONS.md](docs/DECISIONS.md) - Architecture decisions
- [EXAMPLES.md](docs/EXAMPLES.md) - Usage examples
- [CHANGELOG.md](docs/CHANGELOG.md) - Change history

## Troubleshooting

### "Ollama is not available"

If you see this error and want to use prompt optimization:
1. Install Ollama from https://ollama.ai
2. Pull a model: `ollama pull svjack/gpt-oss-20b-heretic`
3. Verify it works: `ollama list`

You can generate images without Ollama by skipping optimization.

### "OpenRouter API key is required"

Make sure you've set the `OPENROUTER_API_KEY` environment variable or configured it in your `.env` file.

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
