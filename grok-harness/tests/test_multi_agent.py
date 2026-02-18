#!/usr/bin/env python
"""
Test multi-agent spawning and delegation.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grok_harness.core.config_manager import ConfigManager
from grok_harness.core.grok_client import GrokClient
from grok_harness.core.session_manager import SessionManager


async def test_multi_agent() -> None:
    """Test spawning and delegating to sub-agents."""
    import os

    print("\nTesting Multi-Agent Support")
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

        print("\nTest 1: Create coordinator session")
        main_id = await session_manager.create_session(
            name="coordinator",
            soul_prompt=(
                "You are a coordinator agent. "
                "Delegate tasks to specialist agents when appropriate."
            ),
        )
        print(f"  Created main agent: {main_id}")

        print("\nTest 2: List sessions")
        sessions = session_manager.list_sessions()
        assert len(sessions) >= 1, "Should have at least one session"
        print(f"  Active sessions: {len(sessions)}")
        for s in sessions:
            print(f"    - {s['name']} ({s['session_id']}): {s['status']}")

        print("\nTest 3: Send message (simple task)")
        result = await session_manager.send_message(
            main_id,
            "What is 2 + 2? Reply with just the number.",
        )
        if result.get("success"):
            print(f"  Response: {result.get('result')}")
        else:
            print(f"  Error: {result.get('error')}")

        print("\nTest 4: Clean up")
        for s in sessions:
            await session_manager.terminate_session(s["session_id"])
        remaining = session_manager.list_sessions()
        assert len(remaining) == 0, "Sessions should be terminated"
        print("  All sessions terminated")

    print("\nDone")


if __name__ == "__main__":
    asyncio.run(test_multi_agent())
