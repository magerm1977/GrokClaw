"""
Named agent for natural conversation with tool access.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.grok_client import GrokClient
from ..memory.unified import UnifiedMemory
from ..tools.current_events import CurrentEventsTool
from ..tools.site_analyzer import SiteAnalyzer
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
        session_dir: Optional[Path] = None,
    ) -> None:
        self.name = name
        self.grok = grok
        self.memory = memory
        self.session_dir = session_dir or Path.home() / ".grok-harness"
        self.storage_dir = self.session_dir / "agent_data"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.storage_dir / f"{name.lower()}_state.json"
        self.conversation_history: List[Dict[str, Any]] = []
        self.max_history = 50
        self.user_provided_date: Optional[datetime] = None
        self.date_confirmed = False
        self.system_date = datetime.now()
        self._load_state()
        self.system_prompt = f"""You are {name}, a helpful AI assistant with access to tools.
You can check weather, browse websites, and remember past conversations.
Be friendly, concise, and helpful. If you need to use a tool, explain what you're doing.

Available tools:
- weather: Get current weather or forecast for any location
- browse: Visit a URL and read content
- memory: Remember important information from our conversation

When using weather, just call it directly - no browser needed.
You can also analyze websites: when given a URL, use the site analysis to provide accurate, content-based insights.

NEVER cite timeanddate.com for date verification. Date is verified via worldtimeapi, timeapi, or system time only."""

    def _load_state(self) -> None:
        """Load saved agent state from disk."""
        try:
            if self.state_file.exists():
                state = json.loads(self.state_file.read_text(encoding="utf-8"))
            else:
                # Migrate from old chat_sessions.json if present
                old_file = self.session_dir / "chat_sessions.json"
                if old_file.exists():
                    data = json.loads(old_file.read_text(encoding="utf-8"))
                    state = data.get(self.name, {})
                else:
                    return

            dt_str = state.get("user_provided_date")
            if dt_str:
                self.user_provided_date = datetime.fromisoformat(dt_str)
                self.date_confirmed = bool(state.get("date_confirmed", True))
        except Exception:
            pass

    def _save_state(self) -> None:
        """Save agent state to disk."""
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            state: Dict[str, Any] = {
                "user_provided_date": (
                    self.user_provided_date.isoformat() if self.user_provided_date else None
                ),
                "date_confirmed": self.date_confirmed,
                "last_updated": datetime.now().isoformat(),
            }
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text."""
        pattern = r"https?://[^\s<>\"']+|www\.[^\s<>\"']+"
        return re.findall(pattern, text)

    def _parse_date_from_message(self, message: str) -> Optional[datetime]:
        """Extract date from user message with various formats."""
        # Pattern 1: "February 16th, 2026" or "Feb 16, 2026"
        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        pattern1 = (
            r"(january|february|march|april|may|june|july|august|september|"
            r"october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
            r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})"
        )
        match1 = re.search(pattern1, message, re.IGNORECASE)
        if match1:
            month_str = match1.group(1).lower()
            day = int(match1.group(2))
            year = int(match1.group(3))
            month = month_map.get(month_str, 1)
            try:
                return datetime(year, month, day)
            except ValueError:
                return None

        # Pattern 2: "2/16/2026" or "02/16/2026" (US month/day/year)
        pattern2 = r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})"
        match2 = re.search(pattern2, message)
        if match2:
            month, day, year = map(int, match2.groups())
            if 1 <= month <= 12 and 1 <= day <= 31:
                try:
                    return datetime(year, month, day)
                except ValueError:
                    return None

        return None

    async def _handle_date_correction(self, message: str) -> Optional[str]:
        """Handle user date corrections."""
        # Only treat as date correction if message suggests setting the date
        msg_lower = message.lower().strip()
        if not any(
            phrase in msg_lower
            for phrase in [
                "current date is",
                "today is",
                "todays date",
                "today's date",
                "the date is",
                "date is",
                "current time is",
                "set the date",
                "set date to",
                "it's ",
            ]
        ):
            return None

        parsed_date = self._parse_date_from_message(message)
        if not parsed_date:
            return None

        self.user_provided_date = parsed_date
        self.date_confirmed = True
        self._save_state()
        formatted_date = parsed_date.strftime("%B %d, %Y")

        self.conversation_history.append({
            "role": "system",
            "content": f"Current date set to: {formatted_date}",
            "timestamp": datetime.now().isoformat(),
        })
        reply = (
            f"Got it, Mark! I'll use **{formatted_date}** as the current date "
            "going forward. Thanks for the correction!"
        )
        self.conversation_history.append({
            "role": "assistant",
            "content": reply,
            "timestamp": datetime.now().isoformat(),
        })
        return f"[{self.name}]: {reply}"

    def get_current_date(self) -> str:
        """Get the current date (user-provided or system)."""
        if self.user_provided_date:
            return self.user_provided_date.strftime("%B %d, %Y")
        return self.system_date.strftime("%B %d, %Y")

    async def _analyze_url(self, url: str) -> str:
        """
        Properly analyze a URL and provide insights.
        Forces use of actual site data; no hallucinations.
        """
        analysis = await SiteAnalyzer.analyze(url)
        if "error" in analysis:
            return f"Sorry, I couldn't analyze {url}: {analysis['error']}"

        purpose = analysis["purpose_detection"]["primary"].replace("_", " ").title()
        confidence = analysis["purpose_detection"]["confidence"]

        headlines = analysis.get("headlines", {})
        h1_text = headlines.get("h1", ["No headline found"])[0] if headlines.get("h1") else "No headline found"
        key_messages = analysis.get("key_messages", [])
        pricing = analysis.get("pricing", [])
        ctas = analysis.get("ctas", [])

        prompt = f"""You MUST base your analysis ONLY on the following REAL data extracted from {url}.
DO NOT invent or assume anything not in this data.

REAL SITE DATA:
- Title: {analysis['title']}
- Description: {analysis['description']}
- Main Headline: {h1_text}
- Key Messages Found: {key_messages}
- Pricing Info Found: {pricing}
- Call-to-Action Buttons: {ctas}
- Detected Purpose: {purpose} (confidence: {confidence*100:.0f}%)

Based STRICTLY on this data:
1. What is this site's ACTUAL purpose in one sentence?
2. What are the REAL features and pricing?
3. Who is the ACTUAL target audience?
4. Give 3 marketing ideas based ONLY on the actual content shown.

If the data doesn't contain certain information, state "Not found in page content" rather than guessing."""

        if not self.grok:
            return (
                f"Site analysis: {analysis['title']}. Purpose: {purpose}. "
                f"Headline: {h1_text}. Description: {analysis['description'][:200]}"
            )
        try:
            resp = await self.grok.chat_completion(
                [
                    {
                        "role": "system",
                        "content": "You are a precise website analyst. ONLY use the provided data. Never invent or assume.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            return resp["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Analysis complete but Grok failed: {e}. Raw: {analysis['title']} - {analysis['description'][:150]}"

    async def chat(self, message: str) -> str:
        """Have a conversation with the named agent."""
        self.conversation_history.append({
            "role": "user",
            "content": message,
            "timestamp": datetime.now().isoformat(),
        })
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

        # Check for date corrections first
        date_response = await self._handle_date_correction(message)
        if date_response:
            return date_response

        urls = self._extract_urls(message)
        if urls:
            if len(urls) == 1 and message.strip() == urls[0]:
                result = await self._analyze_url(urls[0])
                self.conversation_history.append({
                    "role": "assistant",
                    "content": result,
                    "timestamp": datetime.now().isoformat(),
                })
                return f"[{self.name}]: {result}"
            url_analyses = []
            for u in urls:
                analysis = await SiteAnalyzer.analyze(u)
                if "error" not in analysis:
                    purpose = analysis["purpose_detection"]["primary"]
                    desc = (analysis.get("description") or "")[:100]
                    url_analyses.append(f"URL {u}: {purpose} - {desc}")
            if url_analyses:
                context = message + "\n\nSite analyses:\n" + "\n".join(url_analyses)
                response = await self._get_grok_response(context)
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now().isoformat(),
                })
                return f"[{self.name}]: {response}"

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

    def _normalize_message(self, text: str) -> str:
        """Normalize message for matching (e.g. curly quotes)."""
        return text.replace("\u2019", "'").replace("\u2018", "'").lower().strip()

    async def _handle_simple_commands(self, message: str) -> Optional[str]:
        """Handle simple commands without calling Grok."""
        msg_lower = self._normalize_message(message)

        # "date" or "grok-harness date" - user may be asking for date
        if msg_lower in ("date", "grok-harness date") or msg_lower.endswith(" date"):
            if self.user_provided_date:
                return f"Today is **{self.get_current_date()}** (as you told me earlier)."
            real_info = await CurrentEventsTool.get_current_date()
            if real_info.get("warning"):
                return f"Today is **{real_info['date']}** (system time - {real_info['warning']})"
            return f"Today is **{real_info['date']}** (verified via {real_info['source']})."

        # Explicit /setdate command
        if msg_lower.startswith("/setdate "):
            date_str = message[9:].strip()
            parsed = self._parse_date_from_message(date_str)
            if parsed:
                self.user_provided_date = parsed
                self.date_confirmed = True
                self._save_state()
                formatted = parsed.strftime("%B %d, %Y")
                return (
                    f"Date set to **{formatted}**! I'll remember this for our conversation."
                )
            return (
                "Sorry, I couldn't parse that date. Try formats like "
                "'February 16, 2026' or '2/16/2026'."
            )

        # Date query (strip trailing ? for matching)
        date_queries = (
            "what is the date",
            "what's the date",
            "what is the current date",
            "what's the current date",
            "current date",
            "today's date",
            "whats the date",
            "whats the date now",
            "what's the date now",
        )
        msg_normalized = msg_lower.rstrip("?.").strip()
        # Also match if message contains a date question (handles "what's the date?" with smart quotes)
        is_date_query = (
            msg_normalized in date_queries
            or msg_normalized == "what is the date now"
            or "whats the date" in msg_lower
            or "what's the date" in msg_lower
        )
        if is_date_query:
            if self.user_provided_date:
                return f"Today is **{self.get_current_date()}** (as you told me earlier)."
            real_info = await CurrentEventsTool.get_current_date()
            if real_info.get("warning"):
                return f"Today is **{real_info['date']}** (system time - {real_info['warning']})"
            return f"Today is **{real_info['date']}** (verified via {real_info['source']})"

        # Current year query
        if any(
            phrase in msg_lower
            for phrase in ("this year", "current year", "what year", "what year is it")
        ):
            if self.user_provided_date:
                return f"The current year is **{self.user_provided_date.year}**."
            real_info = await CurrentEventsTool.get_current_date()
            return f"The current year is **{real_info['year']}** (verified via {real_info['source']})."

        # News / current events query
        if any(
            word in msg_lower
            for word in ("news", "current events", "headlines", "what's happening")
        ):
            news = await CurrentEventsTool.get_current_news(limit=5)
            if news:
                lines = ["Here are today's top headlines:"]
                for i, item in enumerate(news, 1):
                    lines.append(f"{i}. {item['title']} ({item['source']})")
                return "\n".join(lines)
            return "Sorry, I couldn't fetch current news right now."

        # "What date did I set?" - remind user of stored date
        if "what date" in msg_lower and ("set" in msg_lower or "tell" in msg_lower):
            if self.user_provided_date:
                return (
                    f"You set the date to **{self.get_current_date()}** earlier in our conversation."
                )
            return "You haven't set a date yet. You can tell me the current date and I'll remember it."

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
                current_date = self.get_current_date()
                if "forecast" in msg_lower or "day" in msg_lower:
                    days = 3
                    if "5-day" in msg_lower or "5 day" in msg_lower:
                        days = 5
                    elif "7-day" in msg_lower or "7 day" in msg_lower:
                        days = 7
                    result = await WeatherTool.get_forecast(location, days)
                    if result.get("success"):
                        return (
                            f"Here's the {days}-day forecast from {current_date} "
                            f"for {location}:\n{result['data']}"
                        )
                else:
                    result = await WeatherTool.get_current(location)
                    if result.get("success"):
                        return (
                            f"Here's the weather for {location} on {current_date}:\n"
                            f"{result['data']}"
                        )
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
        """Get response from Grok with current context."""
        if self.user_provided_date:
            current_date = self.get_current_date()
            current_year = self.user_provided_date.year
        else:
            real_info = await CurrentEventsTool.get_current_date()
            current_date = real_info["date"]
            current_year = real_info["year"]

        news_context = ""
        try:
            news = await CurrentEventsTool.get_current_news(limit=3)
            if news:
                news_context = "\nCurrent headlines:\n" + "\n".join(
                    f"- {n['title']}" for n in news
                )
        except Exception:
            pass

        system_content = f"""{self.system_prompt}

IMPORTANT - CURRENT CONTEXT:
- Current date: {current_date}
- Current year: {current_year}
{news_context}

You MUST use this current date/year for all responses. Do not default to 2024.
Never cite timeanddate.com - date comes from worldtimeapi, timeapi, or system.
If discussing events, assume they are current as of {current_date} unless the user specifies otherwise."""

        messages = [{"role": "system", "content": system_content}]
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
