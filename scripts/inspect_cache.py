#!/usr/bin/env python
"""
Inspect cache contents.

Usage:
    python scripts/inspect_cache.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from genimg.utils.cache import get_cache


def main() -> None:
    """Display cache contents."""
    cache = get_cache()
    
    print("Cache Inspection")
    print("=" * 50)
    print()
    print(f"Cache size: {cache.size()} entries")
    print()
    
    if cache.size() == 0:
        print("Cache is empty")
    else:
        print("Cached entries:")
        # Note: This is a simple implementation
        # In production, you might want to add methods to PromptCache
        # to iterate through entries
        print("(Detail inspection requires cache iteration methods)")
    
    print()
    print("=" * 50)


if __name__ == "__main__":
    main()
