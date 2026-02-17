#!/usr/bin/env python
"""Quick test for date handling."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grok_harness.agent.named_agent import NamedAgent


async def main():
    agent = NamedAgent("TestDate")
    for q in ["date", "grok-harness date", "what's the date?"]:
        r = await agent.chat(q)
        print(f"Q: {q}")
        print(f"A: {r}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
