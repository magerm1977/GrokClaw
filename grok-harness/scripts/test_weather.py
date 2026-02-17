#!/usr/bin/env python
"""
Quick test for weather functionality.
Run: python scripts/test_weather.py "Pensacola, FL"
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from grok_harness.tools.weather import WeatherTool


def _safe_print(s: str) -> None:
    """Print string safe for cp1252 console."""
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode("ascii", "replace").decode("ascii"))


async def main() -> None:
    location = sys.argv[1] if len(sys.argv) > 1 else "Pensacola, FL"
    _safe_print(f"\nTesting weather for: {location}")
    _safe_print("-" * 40)

    current = await WeatherTool.get_current(location)
    if current.get("success"):
        _safe_print(f"Current: {current['data']}")
    else:
        _safe_print(f"Error: {current.get('error')}")

    forecast = await WeatherTool.get_forecast(location, 3)
    if forecast.get("success"):
        _safe_print("\n3-Day Forecast (first 500 chars):")
        _safe_print(forecast["data"][:500])
    else:
        _safe_print(f"Error: {forecast.get('error')}")


if __name__ == "__main__":
    asyncio.run(main())
