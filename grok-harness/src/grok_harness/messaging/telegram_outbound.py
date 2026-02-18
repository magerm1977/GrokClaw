"""
Telegram outbound messaging for proactive agent notifications.

Agents can send messages to you via Telegram without you asking.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import NetworkError, TelegramError, TimedOut

from ..utils.errors import MessagingError

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Send proactive messages from agents to Telegram.

    Features:
    - Message queue for retry on failure
    - Rate limiting protection
    - Encrypted token storage
    - Message templates for different agent types
    """

    def __init__(
        self,
        bot_token: str,
        default_chat_id: Optional[str] = None,
        config_path: Optional[Path] = None,
        encrypt_token: bool = True,
    ):
        self.bot_token = bot_token
        self.default_chat_id = default_chat_id
        self.config_path = config_path or Path.home() / ".grok-harness" / "telegram.json"
        self.encrypt_token = encrypt_token

        self.bot: Optional[Bot] = None
        self._initialized = False
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._queue_processor_task: Optional[asyncio.Task] = None

        self.stats: Dict[str, Any] = {
            "messages_sent": 0,
            "messages_failed": 0,
            "last_message_time": None,
            "total_characters": 0,
        }

        self._load_state()

    def _load_state(self) -> None:
        """Load saved state including encrypted token."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                if data.get("encrypted") and self.encrypt_token:
                    from ..utils.encryption import decrypt_value

                    self.bot_token = decrypt_value(data["bot_token"])
                else:
                    self.bot_token = data.get("bot_token", self.bot_token)
                self.default_chat_id = data.get("default_chat_id", self.default_chat_id)
                self.stats = data.get("stats", self.stats)
            except Exception as e:
                logger.error("Error loading Telegram state: %s", e)

    def _save_state(self) -> None:
        """Save state with encrypted token."""
        try:
            from ..utils.encryption import encrypt_value

            data: Dict[str, Any] = {
                "default_chat_id": self.default_chat_id,
                "stats": self.stats,
                "last_updated": datetime.now().isoformat(),
            }
            if self.encrypt_token:
                data["bot_token"] = encrypt_value(self.bot_token)
                data["encrypted"] = True
            else:
                data["bot_token"] = self.bot_token
                data["encrypted"] = False

            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Error saving Telegram state: %s", e)

    async def initialize(self) -> bool:
        """Initialize bot connection."""
        try:
            self.bot = Bot(token=self.bot_token)
            me = await self.bot.get_me()
            logger.info("Telegram bot connected: @%s (ID: %s)", me.username, me.id)
            self._initialized = True
            self._queue_processor_task = asyncio.create_task(
                self._process_message_queue()
            )
            return True
        except TelegramError as e:
            logger.error("Telegram initialization failed: %s", e)
            raise MessagingError(f"Telegram connection failed: {e}") from e

    async def shutdown(self) -> None:
        """Clean shutdown."""
        if self._queue_processor_task:
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass
        self._save_state()

    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "HTML",
        agent_name: Optional[str] = None,
        priority: int = 0,
    ) -> bool:
        """
        Queue a message to send via Telegram.
        """
        if not self._initialized:
            await self.initialize()

        target_chat = chat_id or self.default_chat_id
        if not target_chat:
            logger.error("No chat_id specified for Telegram message")
            return False

        if agent_name:
            formatted_text = f"<b>{agent_name}</b>:\n{text}"
        else:
            formatted_text = text

        await self._message_queue.put(
            {
                "text": formatted_text,
                "chat_id": target_chat,
                "parse_mode": parse_mode,
                "priority": priority,
                "timestamp": datetime.now().isoformat(),
            }
        )
        return True

    async def _process_message_queue(self) -> None:
        """Background task to process queued messages."""
        while True:
            try:
                msg = await self._message_queue.get()
                success = await self._send_with_retry(msg)
                if success:
                    self.stats["messages_sent"] += 1
                    self.stats["last_message_time"] = datetime.now().isoformat()
                    self.stats["total_characters"] = (
                        self.stats.get("total_characters", 0) + len(msg["text"])
                    )
                else:
                    self.stats["messages_failed"] += 1
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Message queue error: %s", e)
                await asyncio.sleep(1)

    async def _send_with_retry(
        self, msg: Dict[str, Any], max_retries: int = 3
    ) -> bool:
        """Send a message with retry logic."""
        if not self.bot:
            return False
        for attempt in range(max_retries):
            try:
                await self.bot.send_message(
                    chat_id=msg["chat_id"],
                    text=msg["text"],
                    parse_mode=msg.get("parse_mode", "HTML"),
                )
                logger.debug("Message sent to %s", msg["chat_id"])
                return True
            except TimedOut:
                logger.warning("Telegram timeout (attempt %d)", attempt + 1)
                await asyncio.sleep(2**attempt)
            except NetworkError as e:
                logger.warning(
                    "Telegram network error (attempt %d): %s", attempt + 1, e
                )
                await asyncio.sleep(2**attempt)
            except TelegramError as e:
                logger.error("Telegram error (not retryable): %s", e)
                return False
        return False

    async def send_agent_update(
        self,
        agent_name: str,
        update_type: str,
        content: str,
        chat_id: Optional[str] = None,
    ) -> bool:
        """Send a formatted update from an agent."""
        templates = {
            "heartbeat": "Heartbeat\n{content}",
            "alert": "Alert\n{content}",
            "summary": "Daily Summary\n{content}",
            "discovery": "New Discovery\n{content}",
            "error": "Error Report\n{content}",
        }
        template = templates.get(update_type, "{content}")
        formatted = template.format(content=content[:500])
        return await self.send_message(
            text=formatted,
            chat_id=chat_id,
            parse_mode="HTML",
            agent_name=agent_name,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get notification statistics."""
        return {
            **self.stats,
            "queue_size": self._message_queue.qsize(),
            "initialized": self._initialized,
            "default_chat": self.default_chat_id,
        }

    def create_listener(
        self,
        session_manager: Any,
        default_session_id: Optional[str] = None,
    ) -> "TelegramListener":
        """Create a listener for inbound messages."""
        return TelegramListener(self, session_manager, default_session_id)


class TelegramListener:
    """Listen for incoming Telegram messages and route to agents."""

    def __init__(
        self,
        notifier: TelegramNotifier,
        session_manager: Any,
        default_session_id: Optional[str] = None,
    ):
        self.notifier = notifier
        self.session_manager = session_manager
        self.default_session_id = default_session_id
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._update_id = 0
        self.chat_sessions: Dict[str, str] = {}

    async def start(self) -> None:
        """Start polling for messages."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram listener started")

    async def stop(self) -> None:
        """Stop polling."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Telegram listener stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        if not self.notifier.bot:
            return
        while self._running:
            try:
                updates = await self.notifier.bot.get_updates(
                    offset=self._update_id,
                    timeout=30,
                    allowed_updates=["message"],
                )
                for update in updates:
                    self._update_id = update.update_id + 1
                    if update.message and update.message.text:
                        await self._handle_message(update.message)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Telegram poll error: %s", e)
                await asyncio.sleep(5)

    async def _handle_message(self, message: Any) -> None:
        """Handle incoming message."""
        chat_id = str(message.chat.id)
        text = message.text or ""
        user = message.from_user
        username = (
            getattr(user, "username", None) or str(getattr(user, "id", "unknown"))
            if user
            else "unknown"
        )

        logger.info("Telegram message from %s: %s...", username, text[:50])

        session_id = self.chat_sessions.get(chat_id)

        if not session_id:
            if self.default_session_id:
                session_id = self.default_session_id
            else:
                session_id = await self.session_manager.create_session(
                    name=f"telegram_{username}",
                    soul_prompt=(
                        "You are a helpful assistant chatting via Telegram. "
                        "Be concise and friendly."
                    ),
                )
            self.chat_sessions[chat_id] = session_id

        result = await self.session_manager.send_message(
            session_id=session_id,
            message=text,
        )

        if result.get("success"):
            response = result.get("result", "")
            if response:
                resp_str = (
                    str(response)[:4000]
                    if isinstance(response, (dict, list))
                    else str(response)[:4000]
                )
                await self.notifier.send_message(
                    text=resp_str,
                    chat_id=chat_id,
                    agent_name="GrokClaw",
                )
        else:
            await self.notifier.send_message(
                text=f"Error: {result.get('error', 'Unknown error')}",
                chat_id=chat_id,
            )
