#!/usr/bin/env python
"""
Test text-only mode.
"""

import asyncio
import sys
from pathlib import Path

if str(Path(__file__).parent.parent / "src") not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grok_harness.agent.named_agent import NamedAgent


async def test_text_mode() -> None:
    """Test that text-only mode works."""
    agent = NamedAgent("Assistant", grok=None)
    agent.text_only_mode = True

    test_queries = [
        "hello",
        "what is 2+2",
        "what is bitcoin price",
        "what's the weather in London",
    ]

    print("\nTesting Text-Only Mode")
    print("=" * 50)

    for query in test_queries:
        print(f"\nYou: {query}")
        response = await agent.chat(query)
        safe = response.encode("ascii", "replace").decode("ascii")
        print(f"Assistant: {safe[:200]}{'...' if len(safe) > 200 else ''}")
        await asyncio.sleep(0.2)

    print("\n[OK] Text-only mode test complete")
    print("Note: 'hello' needs Grok (set XAI_API_KEY for full test)")


if __name__ == "__main__":
    asyncio.run(test_text_mode())
