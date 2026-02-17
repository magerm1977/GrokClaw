"""Grok Harness - Grok-powered browser automation for GrokClaw."""

import asyncio
import sys

# Fix Windows event loop to avoid asyncio resource warnings
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

__version__ = "0.1.0"
