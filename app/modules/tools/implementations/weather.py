from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import urlopen

from app.modules.tools.base import BaseTool


class WeatherTool(BaseTool):
    name = "weather"
    description = "Gets current weather for a city using geocoding and weather APIs."
    parameters = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name, for example 'Paris' or 'Amman'.",
            },
            "units": {
                "type": "string",
                "description": "Temperature units.",
                "enum": ["celsius", "fahrenheit"],
                "default": "celsius",
            },
        },
        "required": ["city"],
    }

    def run(self, arguments: dict[str, object]) -> str:
        city = str(arguments.get("city", "")).strip()
        if not city:
            return "No city provided."

        units = str(arguments.get("units", "celsius")).strip().lower()
        temperature_unit = "fahrenheit" if units == "fahrenheit" else "celsius"
        windspeed_unit = "mph" if temperature_unit == "fahrenheit" else "kmh"

        lat, lon, location_name = self._resolve_city(city)
        if lat is None or lon is None:
            return f"Could not find weather location for '{city}'."

        params = urlencode(
            {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                "temperature_unit": temperature_unit,
                "windspeed_unit": windspeed_unit,
            }
        )
        weather_url = f"https://api.open-meteo.com/v1/forecast?{params}"

        try:
            with urlopen(weather_url, timeout=8) as response:  # nosec B310
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return "Weather service is currently unavailable. Please try again."

        current = payload.get("current") or {}
        temp = current.get("temperature_2m")
        feels_like = current.get("apparent_temperature")
        weather_code = current.get("weather_code")
        wind_speed = current.get("wind_speed_10m")

        if temp is None:
            return f"Weather data is currently unavailable for '{location_name}'."

        temp_unit_label = "F" if temperature_unit == "fahrenheit" else "C"
        condition = self._weather_code_to_text(weather_code)
        return (
            f"Current weather in {location_name}: {condition}. "
            f"Temperature: {temp}°{temp_unit_label}, feels like {feels_like}°{temp_unit_label}, "
            f"wind: {wind_speed} {windspeed_unit}."
        )

    def _resolve_city(self, city: str) -> tuple[float | None, float | None, str]:
        geo_params = urlencode(
            {"name": city, "count": 1, "language": "en", "format": "json"}
        )
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?{geo_params}"

        try:
            with urlopen(geo_url, timeout=8) as response:  # nosec B310
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None, None, city

        results = payload.get("results") or []
        if not results:
            return None, None, city

        first = results[0]
        name = str(first.get("name") or city)
        country = str(first.get("country") or "").strip()
        location_name = f"{name}, {country}" if country else name
        return first.get("latitude"), first.get("longitude"), location_name

    @staticmethod
    def _weather_code_to_text(code: object) -> str:
        mapping = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow fall",
            73: "Moderate snow fall",
            75: "Heavy snow fall",
            80: "Rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            95: "Thunderstorm",
        }
        if isinstance(code, int):
            return mapping.get(code, "Unknown conditions")
        return "Unknown conditions"
