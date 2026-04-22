"""Weather Tool plugin using Open-Meteo (free, no API key required)."""

from __future__ import annotations

import logging
from typing import Any

import requests

from secretary.plugin import ConfigRequirement, Tool

logger = logging.getLogger(__name__)

# Irvine, CA coordinates
DEFAULT_LAT = 33.6846
DEFAULT_LON = -117.8265

# WMO weather codes to human-readable descriptions
_WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


class WeatherTool(Tool):
    name = "weather"
    description = "Get current weather and forecast"
    config_schema = []  # No config required — Open-Meteo is free

    def initialize(self, config: dict[str, Any]) -> None:
        self._lat = float(config.get("WEATHER_LAT", DEFAULT_LAT))
        self._lon = float(config.get("WEATHER_LON", DEFAULT_LON))

    def tool_declarations(self) -> list[dict]:
        return [
            {
                "name": "get_weather",
                "description": (
                    "Get current weather conditions and today's forecast. "
                    "Returns temperature, conditions, rain chance, and wind."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            }
        ]

    def execute(self, args: dict) -> str:
        return get_weather(self._lat, self._lon)


def get_weather(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON) -> str:
    """Fetch current weather from Open-Meteo. Returns a human-readable summary."""
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "America/Los_Angeles",
                "forecast_days": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        current = data["current"]
        daily = data["daily"]

        temp = round(current["temperature_2m"])
        code = current["weather_code"]
        condition = _WMO_CODES.get(code, "Unknown")
        wind = round(current["wind_speed_10m"])
        humidity = current["relative_humidity_2m"]

        high = round(daily["temperature_2m_max"][0])
        low = round(daily["temperature_2m_min"][0])
        rain_chance = daily["precipitation_probability_max"][0] or 0

        summary = (
            f"Currently {temp}F, {condition.lower()}. "
            f"High {high}F / Low {low}F. "
            f"Wind {wind} mph, humidity {humidity}%. "
            f"Rain chance: {rain_chance}%."
        )

        if rain_chance >= 40:
            summary += " Bring an umbrella!"
        if high >= 90:
            summary += " Stay hydrated — it's hot today!"
        if low <= 50:
            summary += " Bring a jacket!"

        return summary
    except Exception as e:
        logger.warning("Weather fetch failed: %s", e)
        return "Weather unavailable."
