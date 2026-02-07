#!/usr/bin/env python
"""
Benchmark generation and optimization performance.

Usage:
    python scripts/benchmark.py
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from genimg.core.config import Config
from genimg.core.image_gen import generate_image
from genimg.core.prompt import optimize_prompt, check_ollama_available


def main() -> None:
    """Run performance benchmarks."""
    print("Performance Benchmark")
    print("=" * 50)
    print()
    
    config = Config.from_env()
    config.validate()
    
    # Benchmark prompt optimization
    if check_ollama_available():
        print("Benchmarking prompt optimization...")
        test_prompt = "a beautiful landscape"
        
        start = time.time()
        try:
            optimized = optimize_prompt(test_prompt)
            elapsed = time.time() - start
            print(f"✓ Optimization time: {elapsed:.2f}s")
            print(f"  Original length: {len(test_prompt)} chars")
            print(f"  Optimized length: {len(optimized)} chars")
        except Exception as e:
            print(f"❌ Optimization failed: {e}")
    else:
        print("⚠️  Ollama not available, skipping optimization benchmark")
    
    print()
    
    # Benchmark image generation
    print("Benchmarking image generation...")
    test_prompt = "a simple test image: red square on white background"
    
    start = time.time()
    try:
        result = generate_image(
            prompt=test_prompt,
            api_key=config.openrouter_api_key
        )
        elapsed = time.time() - start
        
        print(f"✓ Generation time: {result.generation_time:.2f}s")
        print(f"  Total time (including overhead): {elapsed:.2f}s")
        print(f"  Image size: {len(result.image_data)} bytes")
        print(f"  Bytes per second: {len(result.image_data) / result.generation_time:.0f}")
        
    except Exception as e:
        print(f"❌ Generation failed: {e}")
    
    print()
    print("=" * 50)
    print("Benchmark complete")


if __name__ == "__main__":
    main()
