#!/usr/bin/env python
"""
Test OpenRouter API connection.

Usage:
    python scripts/test_api.py
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from genimg.core.config import Config
from genimg.core.image_gen import generate_image


def main() -> None:
    """Test OpenRouter API connection."""
    print("Testing OpenRouter API connection...")
    print()

    # Check for API key
    config = Config.from_env()
    
    if not config.openrouter_api_key:
        print("❌ OPENROUTER_API_KEY not set")
        print("Set it in .env file or environment variable")
        sys.exit(1)
    
    print(f"✓ API key found: {config.openrouter_api_key[:20]}...")
    
    try:
        config.validate()
        print("✓ API key validated")
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        sys.exit(1)
    
    # Test simple generation
    print()
    print("Testing image generation (this may take 10-30 seconds)...")
    
    try:
        result = generate_image(
            prompt="a simple test image: blue circle on white background",
            api_key=config.openrouter_api_key,
            model=config.default_image_model
        )
        
        print(f"✓ Generation successful!")
        print(f"  - Model: {result.model_used}")
        print(f"  - Time: {result.generation_time:.2f}s")
        print(f"  - Image size: {len(result.image_data)} bytes")
        
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        sys.exit(1)
    
    print()
    print("✅ All tests passed! OpenRouter API is working correctly.")


if __name__ == "__main__":
    main()
