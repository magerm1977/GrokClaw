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
        agent = NamedAgent("Assistant", grok=grok_client)
        response = await agent.chat("What's the weather in Pensacola?")
    """

    def __init__(
        self,
        name: str = "Assistant",
        grok: Optional[GrokClient] = None,
        memory: Optional[UnifiedMemory] = None,
        session_dir: Optional[Path] = None,
    ) -> None:
        self.name = name
        self.grok = grok
        self.memory = memory
        self.session_dir = session_dir or Path.home() / ".grok-harness"
        self.storage_dir = self.session_dir / "agent_memory"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.storage_dir / f"{name.lower()}_memory.json"
        self.conversation_history: List[Dict[str, Any]] = []
        self.max_history = 50
        self.user_provided_date: Optional[datetime] = None
        self.date_confirmed = False
        self.system_date = datetime.now()
        self.user_name: Optional[str] = None
        self.user_preferences: Dict[str, Any] = {}
        self.text_only_mode = False
        self._load_memory()
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

    def _load_memory(self) -> None:
        """Load persistent memory from disk."""
        try:
            data: Dict[str, Any] = {}
            if self.memory_file.exists():
                data = json.loads(self.memory_file.read_text(encoding="utf-8"))
            else:
                # Migrate from agent_data state file
                old_state = self.session_dir / "agent_data" / f"{self.name.lower()}_state.json"
                if old_state.exists():
                    data = json.loads(old_state.read_text(encoding="utf-8"))
                else:
                    old_sessions = self.session_dir / "chat_sessions.json"
                    if old_sessions.exists():
                        sess = json.loads(old_sessions.read_text(encoding="utf-8"))
                        data = sess.get(self.name, {})

            self.user_name = data.get("user_name")
            self.user_preferences = data.get("user_preferences", {})
            dt_str = data.get("user_provided_date")
            if dt_str:
                try:
                    self.user_provided_date = datetime.fromisoformat(dt_str)
                    self.date_confirmed = bool(data.get("date_confirmed", True))
                    if self.user_provided_date.date() != datetime.now().date():
                        self.date_confirmed = False
                except (ValueError, TypeError):
                    self.user_provided_date = None
                    self.date_confirmed = False
            recent = data.get("recent_history", [])
            if recent:
                self.conversation_history = recent[-10:]
            self._check_date_validity()
        except Exception:
            pass

    def _check_date_validity(self) -> None:
        """Unconfirm saved date if it is more than 1 day old."""
        if self.user_provided_date and self.date_confirmed:
            days_diff = (datetime.now() - self.user_provided_date).days
            if days_diff > 1:
                self.date_confirmed = False

    def _save_memory(self) -> None:
        """Save persistent memory to disk."""
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {
                "user_name": self.user_name,
                "user_preferences": self.user_preferences,
                "user_provided_date": (
                    self.user_provided_date.isoformat() if self.user_provided_date else None
                ),
                "date_confirmed": self.date_confirmed,
                "recent_history": self.conversation_history[-10:],
                "last_updated": datetime.now().isoformat(),
            }
            self.memory_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
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

    def _extract_preferences(self, message: str) -> None:
        """Extract user preferences from messages."""
        msg_lower = message.lower()
        changed = False

        # Temperature preference
        if "celsius" in msg_lower or "metric" in msg_lower:
            if self.user_preferences.get("temperature_unit") != "celsius":
                self.user_preferences["temperature_unit"] = "celsius"
                changed = True
        elif "fahrenheit" in msg_lower or "imperial" in msg_lower:
            if self.user_preferences.get("temperature_unit") != "fahrenheit":
                self.user_preferences["temperature_unit"] = "fahrenheit"
                changed = True

        # Location from weather/forecast requests
        if any(w in msg_lower for w in ("weather", "forecast")):
            loc_match = re.search(
                r"(?:weather|forecast)[^.]*(?:in|for)\s+([A-Za-z0-9\s,]+?)(?:\?|$|\.|\))",
                message,
                re.I,
            )
            if not loc_match:
                loc_match = re.search(
                    r"(?:in|for)\s+([A-Za-z0-9\s,]+?)(?:\?|$|\.)",
                    message,
                    re.I,
                )
            if loc_match:
                loc = loc_match.group(1).strip()
                if loc and len(loc) > 1 and len(loc) < 50:
                    if self.user_preferences.get("last_location") != loc:
                        self.user_preferences["last_location"] = loc
                        changed = True

        if changed:
            self._save_memory()

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
        self._save_memory()
        formatted_date = parsed_date.strftime("%B %d, %Y")

        self.conversation_history.append({
            "role": "system",
            "content": f"Current date set to: {formatted_date}",
            "timestamp": datetime.now().isoformat(),
        })
        reply = (
            f"Got it! I'll use **{formatted_date}** as the current date "
            "going forward. Thanks for the correction!"
        )
        self.conversation_history.append({
            "role": "assistant",
            "content": reply,
            "timestamp": datetime.now().isoformat(),
        })
        return f"[{self.name}]: {reply}"

    def get_current_date(self) -> str:
        """Get the current date - uses user date only if confirmed and from today."""
        if (
            self.user_provided_date
            and self.date_confirmed
            and self.user_provided_date.date() == datetime.now().date()
        ):
            return self.user_provided_date.strftime("%B %d, %Y")
        return datetime.now().strftime("%B %d, %Y")

    def get_current_year(self) -> int:
        """Get the current year - uses user date only if still valid today."""
        if (
            self.user_provided_date
            and self.date_confirmed
            and self.user_provided_date.date() == datetime.now().date()
        ):
            return self.user_provided_date.year
        return datetime.now().year

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

        self._extract_preferences(message)

        # FIRST: Check for simple commands (ALWAYS works, no browser)
        simple_response = await self._handle_simple_commands(message)
        if simple_response:
            self.conversation_history.append({
                "role": "assistant",
                "content": simple_response,
                "timestamp": datetime.now().isoformat(),
            })
            self._save_memory()
            return f"[{self.name}]: {simple_response}"

        # SECOND: Check for date corrections
        date_response = await self._handle_date_correction(message)
        if date_response:
            return date_response

        # THIRD: In text-only mode, use Grok directly (skip URL analysis)
        if self.text_only_mode:
            if self.grok:
                response = await self._get_grok_response(message)
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now().isoformat(),
                })
                self._save_memory()
                return f"[{self.name}]: {response}"
            return (
                f"[{self.name}]: I'm in text-only mode. "
                "Please configure browser for full functionality."
            )

        urls = self._extract_urls(message)
        if urls:
            if len(urls) == 1 and message.strip() == urls[0]:
                result = await self._analyze_url(urls[0])
                self.conversation_history.append({
                    "role": "assistant",
                    "content": result,
                    "timestamp": datetime.now().isoformat(),
                })
                self._save_memory()
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
                self._save_memory()
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
        self._save_memory()
        return f"[{self.name}]: {response}"

    def _normalize_message(self, text: str) -> str:
        """Normalize message for matching (e.g. curly quotes)."""
        return text.replace("\u2019", "'").replace("\u2018", "'").lower().strip()

    async def _handle_simple_commands(self, message: str) -> Optional[str]:
        """Handle simple commands without calling Grok or browser."""
        msg_lower = self._normalize_message(message)

        # ----- BASIC MATH -----
        math_queries = {
            "2+2": "4",
            "5+5": "10",
            "10*10": "100",
            "100/2": "50",
        }
        msg_no_spaces = msg_lower.replace(" ", "")
        for query, answer in math_queries.items():
            if query in msg_no_spaces:
                return f"**{answer}**"
        if re.match(r"^[\d\s\+\-\*\/\(\)\.]+$", message.replace(" ", "")):
            try:
                result = eval(message, {"__builtins__": {}}, {})
                return f"The result is: **{result}**"
            except Exception:
                pass

        # ----- AGENT NAME -----
        if any(
            q in msg_lower
            for q in ("what is your name", "your name", "who are you")
        ):
            return (
                f"My name is **{self.name}**. "
                "I'm your AI assistant powered by Grok!"
            )

        # ----- BASIC INFO -----
        if any(
            q in msg_lower
            for q in ("what is 2+2", "2+2", "what is 2 + 2")
        ):
            return "2 + 2 = **4**"

        # ----- CRYPTO PRICES (NO BROWSER) -----
        if any(
            phrase in msg_lower
            for phrase in ("bitcoin price", "btc price", "crypto price")
        ):
            from ..tools.crypto_price import CryptoPriceTool

            return await CryptoPriceTool.get_price_message()

        # ----- WEATHER (NO BROWSER, wttr fallback) -----
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
            raw_location = (
                location_match.group(1).strip() if location_match else ""
            )
            skip_words = ("what", "how", "is", "the", "weather", "forecast", "today")
            location = (
                raw_location
                if raw_location
                and not any(w in raw_location.lower() for w in skip_words)
                else self.user_preferences.get("last_location", "")
            )
            if location:
                if "forecast" in msg_lower or "day" in msg_lower:
                    days = 5 if "5" in message else 7 if "7" in message else 3
                    result = await WeatherTool.get_forecast(location, days)
                    if result.get("success"):
                        return (
                            f"Here's the {days}-day forecast for {location}:\n"
                            f"{result['data']}"
                        )
                else:
                    result = await WeatherTool.get_current(location)
                    if result.get("success"):
                        return (
                            f"Here's the weather for {location}:\n"
                            f"{result['data']}"
                        )
                    # Fallback to wttr.in (still no browser)
                    try:
                        import aiohttp

                        url = (
                            f"https://wttr.in/{location.replace(' ', '+')}"
                            "?format=%l:+%c+%t+%w&m"
                        )
                        async with aiohttp.ClientSession() as session:
                            async with session.get(
                                url,
                                timeout=aiohttp.ClientTimeout(total=5),
                            ) as resp:
                                if resp.status == 200:
                                    text = (await resp.text()).strip()
                                    return f"Weather for {location}:\n{text}"
                    except Exception:
                        pass
                return (
                    f"Sorry, I couldn't get the weather: "
                    f"{result.get('error', 'Unknown error')}"
                )
            return "Please specify a location, e.g., 'weather in London'"

        # ----- DATE (NO BROWSER) -----
        date_queries = (
            "what is the date",
            "what's the date",
            "current date",
            "today",
            "whats the date",
        )
        if any(q in msg_lower for q in date_queries):
            date_str = self.get_current_date()
            return f"Today is **{date_str}**"

        # ----- TIME (NO BROWSER) -----
        if any(
            q in msg_lower
            for q in ("what time is it", "current time")
        ):
            now = datetime.now()
            return f"The current time is **{now.strftime('%I:%M %p')}**"

        # ----- HELP -----
        if msg_lower in ("help", "what can you do"):
            return f"""I'm {self.name}, your AI assistant! I can:

- **Weather**: "weather in London"
- **Crypto**: "bitcoin price"
- **Math**: "2 + 2"
- **Date**: "what's the date"
- **Time**: "what time is it"
- **Chat**: Just talk to me naturally!

For complex tasks, I can browse websites and use tools."""

        # ----- USER NAME QUERY -----
        if (
            "what is my name" in msg_lower
            or "do you remember my name" in msg_lower
        ):
            if self.user_name:
                return f"Your name is **{self.user_name}**!"
            return "You haven't told me your name yet. What should I call you?"

        # Name introduction
        name_match = re.search(
            r"(?:my name is|i'm|i am|call me)\s+([A-Za-z]+)",
            message,
            re.I,
        )
        if name_match:
            self.user_name = name_match.group(1)
            self._save_memory()
            return f"Nice to meet you, **{self.user_name}**! I'll remember that."

        # "remember" + preference - store for context
        if "remember" in msg_lower and (
            "prefer" in msg_lower or "like" in msg_lower or "want" in msg_lower
        ):
            self.user_preferences["last_note"] = message[:200]
            self._save_memory()

        # "date" or "grok-harness date" - user may be asking for date
        if msg_lower in ("date", "grok-harness date") or msg_lower.endswith(" date"):
            date_str = self.get_current_date()
            if (
                self.user_provided_date
                and self.date_confirmed
                and self.user_provided_date.date() == datetime.now().date()
            ):
                return f"Today is **{date_str}** (matches what you told me)."
            return f"Today is **{date_str}** (system time)."

        # Explicit /setdate command
        if msg_lower.startswith("/setdate "):
            date_str = message[9:].strip()
            parsed = self._parse_date_from_message(date_str)
            if parsed:
                self.user_provided_date = parsed
                self.date_confirmed = True
                self._save_memory()
                formatted = parsed.strftime("%B %d, %Y")
                return (
                    f"Date set to **{formatted}**! I'll remember this for our conversation."
                )
            return (
                "Sorry, I couldn't parse that date. Try formats like "
                "'February 16, 2026' or '2/16/2026'."
            )

        # Current year query
        if any(
            phrase in msg_lower
            for phrase in ("this year", "current year", "what year", "what year is it")
        ):
            year = self.get_current_year()
            return f"The current year is **{year}**."

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

        return None

    async def _get_grok_response(self, message: str) -> str:
        """Get response from Grok with current context."""
        current_date = self.get_current_date()
        current_year = self.get_current_year()

        news_context = ""
        try:
            news = await CurrentEventsTool.get_current_news(limit=3)
            if news:
                news_context = "\nCurrent headlines:\n" + "\n".join(
                    f"- {n['title']}" for n in news
                )
        except Exception:
            pass

        user_ctx = ""
        if self.user_name:
            user_ctx = f"\nUser's name is {self.user_name}."
        if self.user_preferences:
            user_ctx += f"\nUser preferences/notes: {self.user_preferences}"
        system_content = f"""{self.system_prompt}
{user_ctx}

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
