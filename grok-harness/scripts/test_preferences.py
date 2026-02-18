#!/usr/bin/env python
"""Test preference extraction."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode())


async def main() -> None:
    from grok_harness.agent.named_agent import NamedAgent

    agent = NamedAgent("PrefTest")
    r1 = await agent.chat("weather in London")
    safe_print(f"1: {r1[:90]}...")
    r2 = await agent.chat("Remember I prefer Celsius")
    safe_print(f"2: {r2[:70]}")
    r3 = await agent.chat("what is the weather?")
    safe_print(f"3: {r3[:120]}")
    safe_print(f"Preferences: {agent.user_preferences}")


if __name__ == "__main__":
    asyncio.run(main())
