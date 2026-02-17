"""
Current events and real-time information tool.
Uses reliable, free APIs that do not block requests.
"""

from datetime import datetime
from typing import Any, Dict, List

import aiohttp


def _parse_worldtimeapi(data: dict) -> str:
    dt = data.get("datetime", "")
    return dt.split("T")[0] if "T" in dt else dt


def _parse_timeapi(data: dict) -> str:
    dt = data.get("dateTime") or data.get("date", "")
    if not dt:
        return ""
    return dt.split("T")[0] if "T" in str(dt) else str(dt)[:10]


def _parse_worldclockapi(data: dict) -> str:
    dt = data.get("currentDateTime", "")
    return dt.split("T")[0] if "T" in dt else dt


class CurrentEventsTool:
    """Fetch current events, news, and real-time information."""

    DATE_APIS: List[Dict[str, Any]] = [
        {
            "name": "worldtimeapi",
            "url": "https://worldtimeapi.org/api/timezone/Etc/UTC",
            "parser": _parse_worldtimeapi,
        },
        {
            "name": "timeapi",
            "url": "https://timeapi.io/api/Time/current/zone?timeZone=UTC",
            "parser": _parse_timeapi,
        },
        {
            "name": "worldclockapi",
            "url": "https://worldclockapi.com/api/json/utc/now",
            "parser": _parse_worldclockapi,
        },
    ]

    HEADERS = {"User-Agent": "GrokHarness/1.0"}

    @staticmethod
    async def get_current_date() -> Dict[str, Any]:
        """Get current date from multiple reliable APIs."""
        timeout = aiohttp.ClientTimeout(total=5)
        for api in CurrentEventsTool.DATE_APIS:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        api["url"],
                        timeout=timeout,
                        headers=CurrentEventsTool.HEADERS,
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            date_str = api["parser"](data)
                            if not date_str:
                                continue
                            try:
                                parsed = datetime.strptime(date_str, "%Y-%m-%d")
                                return {
                                    "success": True,
                                    "date": parsed.strftime("%B %d, %Y"),
                                    "year": parsed.year,
                                    "month": parsed.month,
                                    "day": parsed.day,
                                    "source": api["name"],
                                }
                            except ValueError:
                                continue
            except Exception:
                continue

        now = datetime.now()
        return {
            "success": True,
            "date": now.strftime("%B %d, %Y"),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "source": "system",
            "warning": "Using system time - verify accuracy",
        }

    @staticmethod
    async def get_current_datetime() -> Dict[str, Any]:
        """Get current date and time (legacy format)."""
        result = await CurrentEventsTool.get_current_date()
        dt_str = f"{result['year']:04d}-{result['month']:02d}-{result['day']:02d}T00:00:00"
        return {
            "success": result["success"],
            "datetime": dt_str,
            "sources": [result["source"]],
        }

    @staticmethod
    async def get_todays_date() -> str:
        """Get today's date in human-readable format."""
        result = await CurrentEventsTool.get_current_date()
        return result["date"]

    @staticmethod
    async def get_current_year() -> int:
        """Get the current year."""
        result = await CurrentEventsTool.get_current_date()
        return result["year"]

    @staticmethod
    async def verify_current_year() -> int:
        """Get and verify the current year."""
        result = await CurrentEventsTool.get_current_date()
        return result["year"]

    @staticmethod
    async def get_current_news(limit: int = 5) -> List[Dict[str, str]]:
        """Get current news headlines."""
        timeout = aiohttp.ClientTimeout(total=5)
        item_timeout = aiohttp.ClientTimeout(total=3)

        # Try Hacker News first (most reliable)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://hacker-news.firebaseio.com/v0/topstories.json",
                    timeout=timeout,
                    headers=CurrentEventsTool.HEADERS,
                ) as resp:
                    if resp.status == 200:
                        story_ids = await resp.json()
                        if not story_ids:
                            raise ValueError("No stories")

                        stories: List[Dict[str, str]] = []
                        for sid in story_ids[: min(limit, 15)]:
                            try:
                                async with session.get(
                                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                                    timeout=item_timeout,
                                    headers=CurrentEventsTool.HEADERS,
                                ) as item_resp:
                                    if item_resp.status != 200:
                                        continue
                                    item = await item_resp.json()
                                    if not item or item.get("type") != "story":
                                        continue
                                    stories.append({
                                        "title": item.get("title", ""),
                                        "url": item.get("url")
                                        or f"https://news.ycombinator.com/item?id={sid}",
                                        "source": "Hacker News",
                                        "time": "",
                                    })
                                    if len(stories) >= limit:
                                        break
                            except Exception:
                                continue
                        if stories:
                            return stories
        except Exception:
            pass

        # Reddit fallback
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://www.reddit.com/r/all/top/.json?limit=5&t=day",
                    headers=CurrentEventsTool.HEADERS,
                    timeout=timeout,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        stories = []
                        for child in data.get("data", {}).get("children", [])[:limit]:
                            d = child.get("data", {})
                            stories.append({
                                "title": d.get("title", ""),
                                "url": d.get("url", ""),
                                "source": "Reddit",
                                "time": "",
                            })
                        if stories:
                            return stories
        except Exception:
            pass

        return []
