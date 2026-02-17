#!/usr/bin/env python
"""
Test current events and date awareness.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def safe_print(text: str) -> None:
    """Print with fallback for Windows console encoding."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode())


async def test_current_events() -> None:
    """Test date and news awareness."""
    from grok_harness.agent.named_agent import NamedAgent
    from grok_harness.tools.current_events import CurrentEventsTool

    agent = NamedAgent("Fred")

    tests = [
        "what's the current date?",
        "what year is it?",
        "tell me today's headlines",
        "set date to February 16, 2026",
        "what's the date now?",
        "what's happening in the world today?",
    ]

    safe_print("\nTesting Current Events Awareness")
    safe_print("=" * 60)

    for test in tests:
        safe_print(f"\nYou: {test}")
        response = await agent.chat(test)
        safe_print(f"Fred: {response}")
        await asyncio.sleep(0.2)


async def test_tool_directly() -> None:
    """Test CurrentEventsTool directly."""
    from grok_harness.tools.current_events import CurrentEventsTool

    safe_print("\n--- Direct Tool Test ---")
    dt = await CurrentEventsTool.get_current_datetime()
    safe_print(f"Datetime: {dt}")

    date_str = await CurrentEventsTool.get_todays_date()
    safe_print(f"Today's date: {date_str}")

    year = await CurrentEventsTool.get_current_year()
    safe_print(f"Current year: {year}")

    news = await CurrentEventsTool.get_current_news(limit=3)
    safe_print(f"News items: {len(news)}")
    for item in news[:2]:
        safe_print(f"  - {item.get('title', '')[:60]}...")


if __name__ == "__main__":
    asyncio.run(test_tool_directly())
    asyncio.run(test_current_events())
