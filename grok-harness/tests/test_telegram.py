#!/usr/bin/env python
"""
Test Telegram integration (requires configured telegram.json).
"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def test_telegram() -> None:
    """Test Telegram outbound messaging."""
    print("\nTesting Telegram Integration")
    print("=" * 60)

    config_path = Path.home() / ".grok-harness" / "telegram.json"
    if not config_path.exists():
        print("SKIP: Telegram not configured. Run 'grok-harness telegram onboard' first.")
        return

    with open(config_path) as f:
        telegram_config = json.load(f)

    from grok_harness.utils.encryption import decrypt_value
    from grok_harness.messaging.telegram_outbound import TelegramNotifier

    token = telegram_config["bot_token"]
    if telegram_config.get("encrypted"):
        token = decrypt_value(token)

    notifier = TelegramNotifier(
        bot_token=token,
        default_chat_id=telegram_config.get("default_chat_id"),
        encrypt_token=False,
    )

    await notifier.initialize()

    tests = [
        ("heartbeat", "All systems operational"),
        ("alert", "CPU usage at 90%"),
        ("summary", "Processed 150 tasks today"),
        ("discovery", "Found new AI research paper"),
        ("error", "Failed to connect to database"),
    ]

    for msg_type, content in tests:
        print(f"\nSending {msg_type}...")
        await notifier.send_agent_update(
            agent_name="TestBot",
            update_type=msg_type,
            content=content,
        )
        await asyncio.sleep(2)

    print("\nStats:", notifier.get_stats())
    await notifier.shutdown()
    print("Done")


if __name__ == "__main__":
    asyncio.run(test_telegram())
