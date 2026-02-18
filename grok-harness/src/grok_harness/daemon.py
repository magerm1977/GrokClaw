"""
Daemon mode for running GrokClaw continuously.

Runs session manager and heartbeat engine in the background.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from .core.config_manager import ConfigManager
from .core.providers import get_llm_client_from_config
from .core.heartbeat import HeartbeatEngine, HeartbeatConfig

logger = logging.getLogger(__name__)


class GrokClawDaemon:
    """Long-running daemon for GrokClaw."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        self.config = ConfigManager.load_config(config_path)
        if not hasattr(self.config, "memory"):
            self.config = ConfigManager.create_default_config()

        self.grok = None
        self.session_manager: Optional[SessionManager] = None
        self.heartbeat: Optional[HeartbeatEngine] = None
        self.telegram = None
        self.telegram_listener = None
        self._running = False

    async def start(self) -> None:
        """Start all daemon components."""
        logger.info("Starting GrokClaw daemon...")

        try:
            self.grok = get_llm_client_from_config(self.config)
            await self.grok.__aenter__()
        except (ValueError, ImportError):
            pass

        self.session_manager = SessionManager(self.config, self.grok)

        interval = getattr(self.config, "heartbeat_interval", 1800)
        proactive_tasks = getattr(self.config, "proactive_tasks", None)
        heartbeat_config = HeartbeatConfig(
            interval_seconds=interval,
            proactive_tasks=proactive_tasks,
        )

        telegram_config_path = Path.home() / ".grok-harness" / "telegram.json"
        if telegram_config_path.exists():
            try:
                with open(telegram_config_path) as f:
                    tg_cfg = json.load(f)
                from .utils.encryption import decrypt_value
                from .messaging.telegram_outbound import TelegramNotifier

                token = tg_cfg["bot_token"]
                if tg_cfg.get("encrypted"):
                    token = decrypt_value(token)
                self.telegram = TelegramNotifier(
                    bot_token=token,
                    default_chat_id=tg_cfg.get("default_chat_id"),
                    encrypt_token=False,
                )
                await self.telegram.initialize()
                self.telegram_listener = self.telegram.create_listener(
                    session_manager=self.session_manager,
                )
                await self.telegram_listener.start()
                logger.info("Telegram integration enabled")
            except Exception as e:
                logger.warning("Telegram init failed: %s", e)

        self.heartbeat = HeartbeatEngine(
            self.session_manager,
            heartbeat_config,
            telegram_notifier=self.telegram,
        )
        await self.heartbeat.start()

        self._running = True
        logger.info("GrokClaw daemon started")

    async def stop(self) -> None:
        """Stop all daemon components."""
        logger.info("Stopping GrokClaw daemon...")

        if self.heartbeat:
            await self.heartbeat.stop()
        if self.telegram_listener:
            await self.telegram_listener.stop()
        if self.telegram:
            await self.telegram.shutdown()

        if self.grok:
            await self.grok.__aexit__(None, None, None)

        self._running = False
        logger.info("GrokClaw daemon stopped")

    async def run(self) -> None:
        """Main daemon loop."""
        await self.start()

        try:
            while self._running:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await self.stop()
