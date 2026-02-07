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

- Python 3.8 or higher
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
GENIMG_DEFAULT_MODEL=google/gemini-2.0-flash-exp-image:free
GENIMG_OPTIMIZATION_MODEL=llama3.2
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

Then open your browser to the displayed URL (typically http://localhost:7860).

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
    model="google/gemini-2.0-flash-exp-image:free"
)

# Save the image
with open("output.png", "wb") as f:
    f.write(result.image_data)

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

The default model is `google/gemini-2.0-flash-exp-image:free`. You can use any OpenRouter-compatible image generation model. Popular options include:

- `google/gemini-2.0-flash-exp-image:free` (default, free tier)
- Check [OpenRouter's model list](https://openrouter.ai/models) for more options

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
# Run all tests
make test

# Run only unit tests
make test-unit

# Run with coverage
make coverage
```

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

- [SPEC.md](SPEC.md) - Complete functional specification (product)
- [LIBRARY_SPEC.md](LIBRARY_SPEC.md) - Library technical specification (underlying API)
- [AGENT.md](AGENT.md) - AI agent development guide
- [DEVELOPMENT.md](DEVELOPMENT.md) - Developer guide
- [DECISIONS.md](DECISIONS.md) - Architecture decisions
- [EXAMPLES.md](EXAMPLES.md) - Usage examples
- [CHANGELOG.md](CHANGELOG.md) - Change history

## Troubleshooting

### "Ollama is not available"

If you see this error and want to use prompt optimization:
1. Install Ollama from https://ollama.ai
2. Pull a model: `ollama pull llama3.2`
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
