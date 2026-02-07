# Examples

This document provides concrete, working examples of genimg functionality.

## Table of Contents

1. [Library Usage](#library-usage)
2. [CLI Usage](#cli-usage)
3. [Prompt Examples](#prompt-examples)
4. [API Request/Response Examples](#api-requestresponse-examples)
5. [Error Handling](#error-handling)
6. [Testing Examples](#testing-examples)

## Library Usage

### Basic Image Generation

```python
from genimg import generate_image, Config

# Configure
config = Config.from_env()
config.validate()

# Generate image
result = generate_image(
    prompt="a serene mountain landscape at dawn, misty atmosphere",
    model="google/gemini-2.0-flash-exp-image:free"
)

# Save image
with open("mountain.png", "wb") as f:
    f.write(result.image_data)

print(f"Generated in {result.generation_time:.2f} seconds")
print(f"Used model: {result.model_used}")
```

### With Prompt Optimization

```python
from genimg import generate_image, optimize_prompt, Config

config = Config.from_env()
config.optimization_enabled = True

# Optimize prompt first
original = "a red car"
optimized = optimize_prompt(original)
print(f"Original: {original}")
print(f"Optimized: {optimized}")

# Generate with optimized prompt
result = generate_image(prompt=optimized)

with open("red_car.png", "wb") as f:
    f.write(result.image_data)
```

### With Reference Image

```python
from genimg import generate_image
from genimg.core.reference import process_reference_image

# Process reference image
ref_encoded, ref_hash = process_reference_image("original_car.jpg")

# Generate new image using reference
result = generate_image(
    prompt="same car but painted blue, maintaining all other details",
    reference_image_b64=ref_encoded
)

with open("blue_car.png", "wb") as f:
    f.write(result.image_data)
```

### Error Handling

```python
from genimg import generate_image, ValidationError, APIError, NetworkError

try:
    result = generate_image(prompt="a beautiful sunset")
    # Success
except ValidationError as e:
    print(f"Invalid input: {e}")
    print(f"Field: {e.field}")
except APIError as e:
    print(f"API error: {e}")
    print(f"Status code: {e.status_code}")
except NetworkError as e:
    print(f"Network error: {e}")
    if e.original_error:
        print(f"Original: {e.original_error}")
```

### Custom Configuration

```python
from genimg import Config, generate_image

# Create custom config
config = Config(
    openrouter_api_key="sk-or-v1-...",
    default_image_model="google/gemini-2.0-flash-exp-image:free",
    default_optimization_model="llama3.2",
    optimization_enabled=True,
    max_image_pixels=1_500_000,  # 1.5MP instead of 2MP
    generation_timeout=180  # 3 minutes instead of 5
)

config.validate()

from genimg.core.config import set_config
set_config(config)

# Now use normally
result = generate_image("a sunset")
```

## CLI Usage

### Basic Generation

```bash
# Simple generation
genimg generate "a beautiful sunset over the ocean"

# With output file
genimg generate "a red sports car" --output car.png

# With specific model
genimg generate "a landscape" --model google/gemini-2.0-flash-exp-image:free
```

### With Optimization

```bash
# Enable optimization
genimg generate "a mountain scene" --optimize

# With specific optimization model
genimg generate "a forest" --optimize --optimization-model llama3.2
```

### With Reference Image

```bash
# Using reference
genimg generate "same subject but different style" --reference original.jpg --output styled.png

# With optimization
genimg generate "transform to watercolor painting" --reference photo.jpg --optimize
```

### Test Commands

```bash
# Test prompt optimization
genimg optimize "a simple prompt"

# List available models (if implemented)
genimg models
```

## Prompt Examples

### Before and After Optimization

**Example 1: Simple Subject**

Original:
```
a red car
```

Optimized:
```
A sleek red sports car photographed at golden hour, shot with 85mm lens creating shallow depth of field, parked on coastal highway with ocean backdrop, cinematic lighting with warm sunset tones, professional automotive photography style, high detail, 4k quality
```

**Example 2: Scene Description**

Original:
```
a mountain landscape
```

Optimized:
```
A majestic mountain landscape at dawn, snow-capped peaks catching first light, foreground with alpine meadow filled with wildflowers, misty valleys below, dramatic clouds, shot from elevated viewpoint, wide-angle lens, golden hour lighting, professional nature photography, crisp detail, atmospheric perspective
```

**Example 3: With Reference**

Original (with reference image of a portrait):
```
same person but in cyberpunk style
```

Optimized:
```
Portrait in cyberpunk aesthetic, neon lighting in pink and blue tones, futuristic urban setting with holographic elements, high-tech fashion and accessories, rain-slicked streets in background, cinematic mood lighting, professional portrait photography, maintaining subject's facial features and pose, 4k detail, blade runner inspired atmosphere
```

### Prompts That Work Well

- **Detailed descriptions**: "A cozy coffee shop interior with warm lighting..."
- **Technical specifications**: "...shot with 50mm lens, f/2.8..."
- **Style references**: "...in the style of Monet"
- **Mood descriptors**: "atmospheric, moody, vibrant, serene"

### Prompts That May Need Improvement

- **Too vague**: "nice picture" → Add details about subject, style, mood
- **Too complex**: Very long prompts may dilute focus
- **Contradictory**: "bright dark scene" → Choose consistent attributes

## API Request/Response Examples

### OpenRouter Successful Request

**Request:**
```json
{
  "model": "google/gemini-2.0-flash-exp-image:free",
  "modalities": ["image"],
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "A serene mountain landscape at dawn"
        }
      ]
    }
  ]
}
```

**Response (JSON with base64):**
```json
{
  "id": "gen-abc123",
  "model": "google/gemini-2.0-flash-exp-image:free",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "images": [
          {
            "image_url": {
              "url": "data:image/png;base64,iVBORw0KGgoAAAANS..."
            }
          }
        ]
      }
    }
  ]
}
```

**Response (Direct Image):**
```
Content-Type: image/png
Content-Length: 245632

<binary PNG data>
```

### OpenRouter Error Responses

**401 Unauthorized:**
```json
{
  "error": {
    "message": "Invalid API key",
    "type": "invalid_request_error",
    "code": "invalid_api_key"
  }
}
```

**429 Rate Limit:**
```json
{
  "error": {
    "message": "Rate limit exceeded",
    "type": "rate_limit_error"
  }
}
```

### Ollama Optimization

**Command:**
```bash
echo "You are a prompt engineer..." | ollama run llama3.2
```

**Output:**
```
A sleek red sports car photographed at golden hour, shot with 85mm lens creating shallow depth of field...
```

## Error Handling

### Validation Errors

```python
from genimg import generate_image, ValidationError

try:
    generate_image("")  # Empty prompt
except ValidationError as e:
    print(f"Error: {e}")
    # Error: Prompt cannot be empty
    print(f"Field: {e.field}")
    # Field: prompt
```

### API Errors

```python
from genimg import generate_image, APIError

try:
    result = generate_image("test", api_key="invalid")
except APIError as e:
    print(f"Error: {e}")
    # Error: Authentication failed. Please check your OpenRouter API key.
    print(f"Status: {e.status_code}")
    # Status: 401
```

### Network Errors

```python
from genimg import generate_image, NetworkError

try:
    result = generate_image("test")  # Network down
except NetworkError as e:
    print(f"Error: {e}")
    # Error: Failed to connect to OpenRouter API. Please check your internet connection.
    if e.original_error:
        print(f"Cause: {type(e.original_error).__name__}")
```

### Image Processing Errors

```python
from genimg.core.reference import process_reference_image
from genimg.utils.exceptions import ImageProcessingError

try:
    process_reference_image("corrupted.jpg")
except ImageProcessingError as e:
    print(f"Error: {e}")
    print(f"File: {e.image_path}")
```

## Testing Examples

### Mocking API Calls

```python
import pytest
from unittest.mock import patch, Mock
from genimg.core.image_gen import generate_image

def test_generate_image_success():
    """Test successful image generation with mocked API."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/png"}
    mock_response.content = b"fake image data"
    
    with patch('requests.post', return_value=mock_response):
        result = generate_image("test prompt", api_key="test-key")
        assert result.image_data == b"fake image data"
        assert result.prompt_used == "test prompt"
```

### Testing Prompt Optimization

```python
import pytest
from unittest.mock import patch, Mock
from genimg.core.prompt import optimize_prompt

def test_optimize_prompt():
    """Test prompt optimization with mocked Ollama."""
    mock_process = Mock()
    mock_process.communicate.return_value = ("Optimized prompt here", "")
    mock_process.returncode = 0
    
    with patch('subprocess.Popen', return_value=mock_process):
        result = optimize_prompt("simple prompt")
        assert "Optimized" in result
```

### Testing Image Processing

```python
import pytest
from PIL import Image
from genimg.core.reference import resize_image

def test_resize_large_image():
    """Test resizing image above 2MP."""
    # Create 3MP test image
    large_image = Image.new("RGB", (2000, 1500))
    
    resized = resize_image(large_image, max_pixels=2_000_000)
    
    # Check dimensions reduced
    assert resized.size[0] * resized.size[1] <= 2_000_000
    
    # Check aspect ratio maintained
    original_ratio = 2000 / 1500
    new_ratio = resized.size[0] / resized.size[1]
    assert abs(original_ratio - new_ratio) < 0.01
```

### Using Fixtures

```python
def test_with_sample_image(sample_png_image):
    """Test using a sample image fixture."""
    from genimg.core.reference import load_image
    
    image = load_image(str(sample_png_image))
    assert image.mode in ["RGB", "RGBA"]

def test_with_test_config(test_config):
    """Test using a test configuration."""
    assert test_config.openrouter_api_key
    test_config.validate()  # Should not raise
```
