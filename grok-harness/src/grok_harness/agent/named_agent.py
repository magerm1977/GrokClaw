"""
Named agent for natural conversation with tool access.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..core.grok_client import GrokClient
from ..memory.unified import UnifiedMemory
from ..tools.weather import WeatherTool


class NamedAgent:
    """
    An agent with a name for natural conversation.

    Example:
        fred = NamedAgent("Fred", grok=grok_client)
        response = await fred.chat("What's the weather in Pensacola?")
    """

    def __init__(
        self,
        name: str = "Fred",
        grok: Optional[GrokClient] = None,
        memory: Optional[UnifiedMemory] = None,
    ) -> None:
        self.name = name
        self.grok = grok
        self.memory = memory
        self.conversation_history: List[Dict[str, Any]] = []
        self.max_history = 50
        self.system_prompt = f"""You are {name}, a helpful AI assistant with access to tools.
You can check weather, browse websites, and remember past conversations.
Be friendly, concise, and helpful. If you need to use a tool, explain what you're doing.

Available tools:
- weather: Get current weather or forecast for any location
- browse: Visit a URL and read content
- memory: Remember important information from our conversation

When using weather, just call it directly - no browser needed."""

    async def chat(self, message: str) -> str:
        """Have a conversation with the named agent."""
        self.conversation_history.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

        response = await self._handle_simple_commands(message)
        if response:
            self.conversation_history.append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat(),
            })
            return f"[{self.name}]: {response}"

        if self.grok:
            response = await self._get_grok_response(message)
        else:
            response = (
                f"[{self.name}] I'm not fully configured yet. "
                "Please set up Grok API key."
            )

        self.conversation_history.append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.now().isoformat(),
        })
        return f"[{self.name}]: {response}"

    async def _handle_simple_commands(self, message: str) -> Optional[str]:
        """Handle simple commands without calling Grok."""
        msg_lower = message.lower()

        if any(w in msg_lower for w in ("weather", "temperature", "forecast")):
            location_match = re.search(
                r"(?:weather|temperature|forecast)[\s,]+(?:in|for|at)?\s*([A-Za-z0-9\s,]+?)(?:\?|$|\.)",
                message,
                re.I,
            )
            if not location_match:
                location_match = re.search(
                    r"(?:in|for|at)\s+([A-Za-z0-9\s,]+?)(?:\?|$|\.)",
                    message,
                    re.I,
                )
            location = location_match.group(1).strip() if location_match else ""
            if location:
                if "forecast" in msg_lower or "day" in msg_lower:
                    days = 3
                    if "5-day" in msg_lower or "5 day" in msg_lower:
                        days = 5
                    elif "7-day" in msg_lower or "7 day" in msg_lower:
                        days = 7
                    result = await WeatherTool.get_forecast(location, days)
                else:
                    result = await WeatherTool.get_current(location)
                if result.get("success"):
                    return f"Here's the weather for {location}:\n{result['data']}"
                return f"Sorry, I couldn't get the weather: {result.get('error', 'Unknown error')}"

        if msg_lower in ("help", "what can you do"):
            return f"""I'm {self.name}, your AI assistant! I can:
- Check weather (try: "weather in London")
- Browse websites (try: "visit example.com")
- Remember things (try: "remember my name is Alex")
- Have conversations

Just talk to me naturally!"""

        return None

    async def _get_grok_response(self, message: str) -> str:
        """Get response from Grok."""
        messages = [{"role": "system", "content": self.system_prompt}]
        for msg in self.conversation_history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        try:
            response = await self.grok.chat_completion(
                messages, temperature=0.7
            )
            return response["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Sorry, I had trouble thinking: {str(e)}"

    async def reset_conversation(self) -> None:
        """Reset conversation history."""
        self.conversation_history = []

    def get_history(self) -> List[Dict[str, Any]]:
        """Get conversation history."""
        return self.conversation_history
