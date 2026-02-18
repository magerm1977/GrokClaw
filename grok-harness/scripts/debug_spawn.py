#!/usr/bin/env python
"""
Debug spawn pattern matching.
"""

import re
import sys


def test_pattern(message: str) -> bool:
    """Test if message matches spawn patterns."""
    patterns = [
        r"spawn (?:an? )?(\w+) (?:agent )?(?:to|that|who) (.+)",
        r"create (?:an? )?(\w+) (?:agent )?(?:to|that|who) (.+)",
        r"start (?:an? )?(\w+) (?:agent )?(?:to|that|who) (.+)",
        r"launch (?:an? )?(\w+) (?:agent )?(?:to|that|who) (.+)",
        r"need (?:an? )?(\w+) (?:agent )?(?:to|that|who) (.+)",
    ]

    print(f"\n[Testing] '{message}'")
    print("-" * 40)

    for i, pattern in enumerate(patterns, 1):
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            print(f"[OK] Pattern {i} matched!")
            print(f"     Agent type: {match.group(1)}")
            print(f"     Task: {match.group(2)}")
            return True
        else:
            print(f"[X] Pattern {i} no match")

    return False


if __name__ == "__main__":
    test_message = (
        sys.argv[1] if len(sys.argv) > 1 else "spawn a researcher to find AI news"
    )
    test_pattern(test_message)
