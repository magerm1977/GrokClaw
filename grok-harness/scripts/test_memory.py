#!/usr/bin/env python
"""
Test persistent memory across sessions.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode())


async def test_memory() -> None:
    """Test that memory persists across agent instances."""
    from grok_harness.agent.named_agent import NamedAgent

    safe_print("\nTesting Memory Persistence")
    safe_print("=" * 50)

    # Session 1
    safe_print("\nSession 1:")
    agent = NamedAgent("Assistant")
    for q in [
        "My name is Alex",
        "Remember I prefer Celsius",
        "the date is February 16, 2026",
    ]:
        r = await agent.chat(q)
        safe_print(f"Assistant: {r}")

    safe_print("\n" + "=" * 50)
    safe_print("Simulating new session...")
    safe_print("=" * 50)

    # Session 2 (new agent instance - simulates new process)
    agent2 = NamedAgent("Assistant")
    safe_print("\nSession 2:")
    for q in ["what is my name?", "what's the date?"]:
        r = await agent2.chat(q)
        safe_print(f"Assistant: {r}")


if __name__ == "__main__":
    asyncio.run(test_memory())
