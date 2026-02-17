#!/usr/bin/env python
"""
Test the fixed site analysis with forced real data.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grok_harness.tools.site_analyzer import SiteAnalyzer
from grok_harness.agent.named_agent import NamedAgent
from grok_harness.core.config_manager import ConfigManager
from grok_harness.core.grok_client import GrokClient


async def main() -> None:
    url = "https://coachframe.io"

    print(f"\nTesting FIXED analysis for: {url}")
    print("=" * 60)

    # Step 1: Get REAL data
    print("\nREAL Site Data:")
    analysis = await SiteAnalyzer.analyze(url)

    if "error" in analysis:
        print(f"Error: {analysis['error']}")
        return

    print(f"Title: {analysis['title']}")
    h1 = analysis.get("headlines", {}).get("h1", [])
    print(f"Headline: {h1[0] if h1 else 'N/A'}")
    print(f"Key Messages: {analysis.get('key_messages', [])[:2]}")
    print(f"Pricing: {analysis.get('pricing', [])}")

    # Step 2: Get Fred's analysis (should use REAL data)
    print("\nFred's Analysis (should match REAL data):")
    print("-" * 40)

    config = ConfigManager.load()
    if not config.grok.api_key:
        print("Skipping agent analysis - no API key")
        return

    async with GrokClient(config.grok) as grok:
        agent = NamedAgent("Fred", grok=grok)
        response = await agent.chat(url)
        print(response)


if __name__ == "__main__":
    asyncio.run(main())
