#!/usr/bin/env python
"""
Test date handling in NamedAgent.
"""

import asyncio
import sys
from pathlib import Path

def safe_print(text: str) -> None:
    """Print with fallback for Windows console encoding."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode())

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grok_harness.agent.named_agent import NamedAgent


async def test_date() -> None:
    """Test date correction and memory."""
    agent = NamedAgent("Assistant")

    test_sequence = [
        "what's the date?",
        "the current date is February 16th, 2026",
        "what's the date now?",
        "weather in London",
        "what date did I set earlier?",
    ]

    print("\nTesting Date Handling")
    print("=" * 50)

    for query in test_sequence:
        safe_print(f"\nYou: {query}")
        response = await agent.chat(query)
        safe_print(f"Assistant: {response}")
        await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(test_date())
