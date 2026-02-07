#!/usr/bin/env python
"""
Test Ollama installation and availability.

Usage:
    python scripts/test_ollama.py
"""

import subprocess
import sys


def main() -> None:
    """Test Ollama installation."""
    print("Testing Ollama installation...")
    print()

    # Check if Ollama is in PATH
    try:
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            print(f"✓ Ollama found: {result.stdout.strip()}")
        else:
            print("❌ Ollama command failed")
            sys.exit(1)
            
    except FileNotFoundError:
        print("❌ Ollama not found in PATH")
        print("Install from: https://ollama.ai")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("❌ Ollama command timed out")
        sys.exit(1)
    
    # List installed models
    print()
    print("Installed models:")
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            print(result.stdout)
            
            # Check for recommended model
            if "llama3.2" in result.stdout:
                print("✓ Recommended model (llama3.2) is installed")
            else:
                print("⚠️  Recommended model (llama3.2) not found")
                print("   Install with: ollama pull llama3.2")
        else:
            print("❌ Failed to list models")
            sys.exit(1)
            
    except subprocess.TimeoutExpired:
        print("❌ List command timed out")
        sys.exit(1)
    
    print()
    print("✅ Ollama is installed and working!")


if __name__ == "__main__":
    main()
