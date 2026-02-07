# genimg - AI Image Generation Tool

A Python package for generating AI images with intelligent prompt optimization. Generate high-quality images from simple text descriptions using multiple AI models via OpenRouter, with optional local prompt enhancement via Ollama.

## Features

- 🎨 **Multiple AI Models**: Access various image generation models through OpenRouter
- ✨ **Prompt Optimization**: Automatically enhance prompts using local Ollama models
- 🖼️ **Reference Images**: Use reference images to guide generation
- 💻 **Dual Interface**: Both CLI and web UI (Gradio) interfaces
- 📦 **Library Usage**: Use as a Python library in your own projects
- 🔧 **Type-Safe**: Full type hints for better IDE support

## Installation

### Prerequisites

- Python 3.10 or higher
- OpenRouter API key ([get one here](https://openrouter.ai/keys))
- (Optional) Ollama installed locally for prompt optimization ([install here](https://ollama.ai))

### Install from Source

```bash
# Clone the repository
git clone <repository-url>
cd genimg

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package
pip install -e .

# Install development dependencies (optional)
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

**UI environment variables:**

- `GENIMG_UI_PORT` — Port for the server (default: 7860).
- `GENIMG_UI_HOST` — Host to bind (default: 127.0.0.1). Use `0.0.0.0` for LAN access.
- `GENIMG_UI_SHARE` — Set to `1` or `true` to create a public share link.

### Command Line Interface

Generate an image:

```bash
genimg generate "a red sports car at sunset" --output car.png
```

With prompt optimization:

```bash
genimg generate "a red sports car" --optimize --output car.png
```

With a reference image:

```bash
genimg generate "same car but in blue" --reference original.jpg --output blue_car.png
```

Optimize a prompt without generating:

```bash
genimg optimize "a beautiful landscape"
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
- [LIBRARY_SPEC.md](docs/LIBRARY_SPEC.md) - Library technical specification (underlying API)
- [AGENT.md](AGENT.md) - AI agent development guide
- [DEVELOPMENT.md](docs/DEVELOPMENT.md) - Developer guide
- [DECISIONS.md](docs/DECISIONS.md) - Architecture decisions
- [CLI_PLAN.md](docs/CLI_PLAN.md) - CLI implementation plan
- [GRADIO_UI_PLAN.md](docs/GRADIO_UI_PLAN.md) - Gradio web UI plan (final)
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

Contributions are welcome! Please read [DEVELOPMENT.md](DEVELOPMENT.md) for guidelines.

## Support

- Issues: [GitHub Issues](<repository-issues-url>)
- Discussions: [GitHub Discussions](<repository-discussions-url>)
