"""
Built-in weather tool using wttr.in.
No browser required - direct HTTP calls via aiohttp.
"""

import re
from typing import Any, Dict, Optional

import aiohttp


class WeatherTool:
    """Simple weather fetcher that works without a browser."""

    @staticmethod
    async def get_current(location: str) -> Dict[str, Any]:
        """Get current weather for a location."""
        try:
            location = location.strip().replace(" ", "+")
            url = f"https://wttr.in/{location}?format=%l:+%c+%t+%w+%h&m"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        text = (await resp.text()).strip()
                        return {
                            "success": True,
                            "data": text,
                            "location": location.replace("+", " "),
                            "type": "current",
                        }
                    return {
                        "success": False,
                        "error": f"HTTP {resp.status}",
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    @staticmethod
    async def get_forecast(location: str, days: int = 3) -> Dict[str, Any]:
        """Get weather forecast for a location."""
        try:
            location = location.strip().replace(" ", "+")
            url = f"https://wttr.in/{location}?m&days={days}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        return {
                            "success": True,
                            "data": text,
                            "location": location.replace("+", " "),
                            "days": days,
                            "type": "forecast",
                        }
                    return {
                        "success": False,
                        "error": f"HTTP {resp.status}",
                    }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    @staticmethod
    def parse_weather_text(text: str) -> Dict[str, Any]:
        """Parse weather text into structured data."""
        temp_match = re.search(r"([+-]?\d+°[CF])", text)
        return {
            "temperature": temp_match.group(1) if temp_match else "Unknown",
            "full_text": text[:200],
        }


WEATHER_TOOL = {
    "name": "weather",
    "description": "Get current weather or forecast for any location",
    "functions": {
        "current": WeatherTool.get_current,
        "forecast": WeatherTool.get_forecast,
    },
}
