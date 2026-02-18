"""
Setup wizard for first-time users.
"""

import json
import subprocess
import sys
from pathlib import Path

from rich.prompt import Confirm, Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..core.config_manager import ConfigManager
from .output import console, print_header, print_success, print_warning


class SetupWizard:
    """Interactive setup for new users."""

    async def run(self) -> None:
        """Run the setup wizard."""
        print_header("GrokClaw Setup Wizard")
        console.print("Welcome! Let's get you set up in a few steps.\n")

        # Step 1: API Key
        console.print("[bold]Step 1: Grok API Key[/]")
        console.print(
            "You'll need an API key from xAI (https://console.x.ai)"
        )
        api_key = Prompt.ask("Enter your API key", password=True)

        # Step 2: Browser setup
        console.print("\n[bold]Step 2: Browser Automation[/]")
        if Confirm.ask(
            "Install Playwright for browser automation?", default=True
        ):
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                progress.add_task("Installing Playwright...", total=None)
                subprocess.check_call(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "playwright>=1.40.0",
                    ]
                )
                subprocess.check_call(
                    [
                        sys.executable,
                        "-m",
                        "playwright",
                        "install",
                        "chromium",
                    ]
                )
            print_success("Playwright installed!")

        # Step 3: Telegram (optional)
        console.print("\n[bold]Step 3: Telegram Integration (Optional)[/]")
        if Confirm.ask(
            "Configure Telegram for notifications?", default=False
        ):
            token = Prompt.ask("Enter your Telegram bot token", password=True)
            chat_id = Prompt.ask("Enter your chat ID")
            try:
                from ..messaging.telegram_outbound import TelegramNotifier
                from ..utils.encryption import encrypt_value

                notifier = TelegramNotifier(
                    bot_token=token,
                    default_chat_id=chat_id,
                    encrypt_token=True,
                )
                await notifier.initialize()
                await notifier.send_message("✅ GrokClaw setup complete!")
                await notifier.shutdown()
                print_success("Telegram configured!")

                config_path = Path.home() / ".grok-harness" / "telegram.json"
                config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(config_path, "w") as f:
                    json.dump(
                        {
                            "bot_token": encrypt_value(token),
                            "default_chat_id": chat_id,
                            "encrypted": True,
                            "encrypt": True,
                        },
                        f,
                        indent=2,
                    )
            except Exception as e:
                print_warning(f"Telegram setup failed: {e}")
                print_warning(
                    "You can configure later with: grok-harness telegram onboard"
                )

        # Step 4: Save config
        config = ConfigManager.create_default_config()
        config.grok.api_key = api_key

        config_path = Path.home() / ".grok-harness" / "config.yaml"
        ConfigManager.save_config(config, config_path)
        print_success(f"Configuration saved to {config_path}")

        console.print("\n[bold green]✅ Setup complete![/]")
        console.print("\nTry these commands:")
        console.print("  grok-harness chat 'hello'")
        console.print("  grok-harness agent 'weather in London' --headless")
        console.print("  grok-harness telegram listen")
