"""
Built-in weather tool using wttr.in and fallback APIs.
"""

import re
from typing import Any, Dict, Optional

import aiohttp


class WeatherTool:
    """Reliable weather fetcher with multiple backends."""

    HEADERS = {"User-Agent": "GrokHarness/1.0"}

    @staticmethod
    async def get_current(location: str) -> Dict[str, Any]:
        """Get current weather for a location."""
        try:
            location_clean = location.strip().replace(" ", "+")
            url = f"https://wttr.in/{location_clean}?format=%l:+%c+%t+%w+%h&m"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers=WeatherTool.HEADERS,
                ) as resp:
                    if resp.status == 200:
                        text = (await resp.text()).strip()
                        return {
                            "success": True,
                            "data": text,
                            "location": location_clean.replace("+", " "),
                            "type": "current",
                            "source": "wttr.in",
                        }
            return await WeatherTool._get_current_openmeteo(location_clean)
        except Exception as e:
            try:
                return await WeatherTool._get_current_openmeteo(
                    location.strip().replace(" ", "+")
                )
            except Exception:
                return {"success": False, "error": str(e)}

    @staticmethod
    async def get_forecast(location: str, days: int = 3) -> Dict[str, Any]:
        """Get weather forecast for a location. Uses Open-Meteo (wttr.in returns HTML)."""
        try:
            location_clean = location.strip().replace(" ", "+")
            return await WeatherTool._get_forecast_openmeteo(
                location_clean.replace("+", " "), days
            )
        except Exception as e:
            try:
                return await WeatherTool._get_forecast_openmeteo(
                    location.strip().replace("+", " "), days
                )
            except Exception:
                return {"success": False, "error": str(e)}

    @staticmethod
    async def _get_current_openmeteo(location: str) -> Dict[str, Any]:
        """Fallback: Open-Meteo current weather (no API key)."""
        geo_url = (
            f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(
                geo_url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers=WeatherTool.HEADERS,
            ) as geo_resp:
                if geo_resp.status != 200:
                    return {"success": False, "error": "Location not found"}
                geo_data = await geo_resp.json()
                if not geo_data.get("results"):
                    return {"success": False, "error": "Location not found"}
                lat = geo_data["results"][0]["latitude"]
                lon = geo_data["results"][0]["longitude"]
                name = geo_data["results"][0].get("name", location)

            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                "&current_weather=true&temperature_unit=celsius&windspeed_unit=kmh"
            )
            async with session.get(
                weather_url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers=WeatherTool.HEADERS,
            ) as w_resp:
                if w_resp.status != 200:
                    return {"success": False, "error": "Weather fetch failed"}
                w_data = await w_resp.json()
                cur = w_data["current_weather"]
                temp = cur["temperature"]
                wind = cur["windspeed"]
                cond = WeatherTool._code_to_condition(cur["weathercode"])
                result = f"{name}: {cond} {temp}C, wind {wind}km/h"
                return {
                    "success": True,
                    "data": result,
                    "location": name,
                    "type": "current",
                    "source": "open-meteo",
                }

    @staticmethod
    async def _get_forecast_openmeteo(location: str, days: int) -> Dict[str, Any]:
        """Fallback: Open-Meteo forecast."""
        geo_url = (
            f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(
                geo_url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers=WeatherTool.HEADERS,
            ) as geo_resp:
                if geo_resp.status != 200:
                    return {"success": False, "error": "Location not found"}
                geo_data = await geo_resp.json()
                if not geo_data.get("results"):
                    return {"success": False, "error": "Location not found"}
                lat = geo_data["results"][0]["latitude"]
                lon = geo_data["results"][0]["longitude"]
                name = geo_data["results"][0].get("name", location)

            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&daily=weathercode,temperature_2m_max,temperature_2m_min,"
                f"precipitation_sum,windspeed_10m_max&timezone=auto&forecast_days={days}"
            )
            async with session.get(
                weather_url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers=WeatherTool.HEADERS,
            ) as w_resp:
                if w_resp.status != 200:
                    return {"success": False, "error": "Forecast fetch failed"}
                w_data = await w_resp.json()
                daily = w_data["daily"]
                n = len(daily["time"])
                lines = [f"{days}-day forecast for {name}:"]
                for i in range(n):
                    dt = daily["time"][i]
                    t_max = daily["temperature_2m_max"][i]
                    t_min = daily["temperature_2m_min"][i]
                    precip = daily["precipitation_sum"][i]
                    wind = daily["windspeed_10m_max"][i]
                    cond = WeatherTool._code_to_condition(daily["weathercode"][i])
                    lines.append(
                        f"{dt}: {cond} {t_max}C / {t_min}C, rain {precip}mm, wind {wind}km/h"
                    )
                return {
                    "success": True,
                    "data": "\n".join(lines),
                    "location": name,
                    "days": days,
                    "type": "forecast",
                    "source": "open-meteo",
                }

    @staticmethod
    def _code_to_condition(code: int) -> str:
        """Convert WMO weather code to emoji/condition."""
        codes = {
            0: "Clear",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            56: "Freezing drizzle",
            57: "Dense freezing drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            66: "Freezing rain",
            67: "Heavy freezing rain",
            71: "Slight snow",
            73: "Moderate snow",
            75: "Heavy snow",
            77: "Snow grains",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with hail",
            99: "Heavy thunderstorm with hail",
        }
        return codes.get(code, "Unknown")

    @staticmethod
    def parse_weather_text(text: str) -> Dict[str, Any]:
        """Parse weather text into structured data."""
        temp_match = re.search(r"([+-]?\d+°?[CF]?)", text)
        wind_match = re.search(r"(\d+km/h)", text)
        return {
            "temperature": temp_match.group(1) if temp_match else "Unknown",
            "wind": wind_match.group(1) if wind_match else "Unknown",
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
