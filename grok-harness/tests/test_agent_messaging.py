#!/usr/bin/env python
"""
Test direct agent-to-agent messaging.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grok_harness.core.config_manager import ConfigManager
from grok_harness.core.grok_client import GrokClient
from grok_harness.core.session_manager import SessionManager


async def test_messaging() -> None:
    """Test agents messaging each other."""
    print("\nTesting Agent-to-Agent Messaging")
    print("=" * 60)

    config = ConfigManager.load_config()
    if not hasattr(config, "memory"):
        config = ConfigManager.create_default_config()

    api_key = (
        getattr(config.grok, "api_key", None)
        or os.environ.get("XAI_API_KEY")
        or os.environ.get("GROK_API_KEY")
    )
    if not api_key:
        print("SKIP: No Grok API key (set XAI_API_KEY)")
        return

    async with GrokClient(config.grok) as grok:
        session_manager = SessionManager(config, grok)

        researcher_id = await session_manager.create_session(
            name="researcher",
            soul_prompt="You are a researcher. Find accurate information.",
        )
        print(f"Created researcher: {researcher_id}")

        writer_id = await session_manager.create_session(
            name="writer",
            soul_prompt="You are a writer. Create clear content.",
        )
        print(f"Created writer: {writer_id}")

        print("\nTesting: researcher messages writer")
        result = await session_manager.send_message(
            researcher_id,
            "message writer Please summarize the latest AI news in 2 sentences",
        )

        if result.get("success"):
            res = result.get("result", "")
            if isinstance(res, dict):
                res = str(res)[:300]
            print(f"Response: {res}...")
        else:
            print(f"Failed: {result.get('error')}")

        await session_manager.terminate_session(researcher_id)
        await session_manager.terminate_session(writer_id)
        print("\nDone")


if __name__ == "__main__":
    asyncio.run(test_messaging())
