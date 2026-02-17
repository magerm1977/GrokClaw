#!/usr/bin/env python
"""
Test real date APIs.
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


async def test_date() -> None:
    """Test date APIs."""
    from grok_harness.tools.current_events import CurrentEventsTool

    safe_print("\nTesting Real Date APIs")
    safe_print("=" * 50)

    date_info = await CurrentEventsTool.get_current_date()
    safe_print(f"Date: {date_info['date']}")
    safe_print(f"Source: {date_info['source']}")
    safe_print(f"Year: {date_info['year']}")
    if date_info.get("warning"):
        safe_print(f"Warning: {date_info['warning']}")

    safe_print("\nTesting News API")
    news = await CurrentEventsTool.get_current_news(limit=3)
    for i, item in enumerate(news, 1):
        safe_print(f"{i}. {item['title']} ({item['source']})")


if __name__ == "__main__":
    asyncio.run(test_date())
