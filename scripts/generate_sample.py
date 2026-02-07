#!/usr/bin/env python
"""
Generate a sample image for testing.

Usage:
    python scripts/generate_sample.py [--output FILE] [--prompt TEXT]
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from genimg.core.config import Config
from genimg.core.image_gen import generate_image


def main() -> None:
    """Generate a sample image."""
    parser = argparse.ArgumentParser(description="Generate a sample image")
    parser.add_argument(
        "--output",
        default="sample_output.png",
        help="Output filename (default: sample_output.png)"
    )
    parser.add_argument(
        "--prompt",
        default="a serene mountain landscape at dawn with misty valleys",
        help="Prompt for generation"
    )
    
    args = parser.parse_args()
    
    print(f"Generating image with prompt: {args.prompt}")
    print()
    
    config = Config.from_env()
    config.validate()
    
    try:
        result = generate_image(
            prompt=args.prompt,
            api_key=config.openrouter_api_key
        )
        
        # Save image
        with open(args.output, "wb") as f:
            f.write(result.image_data)
        
        print(f"✓ Image generated successfully!")
        print(f"  - Saved to: {args.output}")
        print(f"  - Generation time: {result.generation_time:.2f}s")
        print(f"  - Model: {result.model_used}")
        
    except Exception as e:
        print(f"❌ Generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
