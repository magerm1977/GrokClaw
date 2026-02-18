#!/usr/bin/env python
"""
Test live chat with persistent date across sessions.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.prompt import Prompt

from grok_harness.agent.named_agent import NamedAgent
from grok_harness.cli.output import console
from grok_harness.core.config_manager import ConfigManager
from grok_harness.core.grok_client import GrokClient


async def main() -> None:
    """Run a persistent chat session."""
    config = ConfigManager.load()

    grok = None
    if config.grok.api_key:
        grok = GrokClient(config.grok)
        await grok.__aenter__()

    agent = NamedAgent(name="Assistant", grok=grok)

    console.print("\n[bold cyan]Testing Live Chat (Persistent Session)[/]")
    console.print("[dim]Type /exit to quit, /reset to reset[/]\n")

    try:
        while True:
            try:
                user_input = Prompt.ask("\n[bold green]You[/]")
                if not user_input:
                    continue

                if user_input.lower() == "/exit":
                    break
                if user_input.lower() == "/reset":
                    await agent.reset_conversation()
                    agent.user_provided_date = None
                    agent.date_confirmed = False
                    agent._save_memory()
                    console.print("[dim]Conversation reset[/]")
                    continue

                response = await agent.chat(user_input)
                console.print(f"[bold blue]Assistant:[/] {response}")

            except (KeyboardInterrupt, EOFError):
                break
    finally:
        if grok:
            await grok.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
