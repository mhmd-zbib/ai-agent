"""
Mock Weather Tool - Demonstrates string parameters and enum validation.

This tool showcases:
- String parameters with validation
- Enum types for controlled options
- Simple JSON return format
- Input validation and error handling
- Comprehensive docstrings
"""

import json
import random
from typing import Any

from app.modules.tools.base import BaseTool
from app.shared.logging import get_logger

logger = get_logger(__name__)


class MockWeatherTool(BaseTool):
    """
    Mock weather lookup tool that returns simulated weather data for cities.

    This tool demonstrates:
    - String parameter handling with validation
    - Enum validation for unit systems (metric/imperial)
    - Structured JSON responses
    - Error handling for invalid inputs
    - Realistic mock data generation

    Examples:
        >>> tool = MockWeatherTool()
        >>> result = tool.run({"city": "London", "units": "metric"})
        >>> # Returns JSON with temperature, conditions, etc.

        >>> result = tool.run({"city": "InvalidCity"})
        >>> # Returns error message for unknown city
    """

    name = "mock_weather"
    description = (
        "Retrieves mock weather information for a specified city. "
        "Returns temperature, conditions, humidity, and wind speed. "
        "Supports metric (Celsius) and imperial (Fahrenheit) units."
    )
    parameters = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "The city name to get weather for (e.g., 'London', 'New York', 'Tokyo')",
            },
            "units": {
                "type": "string",
                "enum": ["metric", "imperial"],
                "description": "Temperature unit system: 'metric' for Celsius or 'imperial' for Fahrenheit",
                "default": "metric",
            },
        },
        "required": ["city"],
    }

    # Mock database of supported cities
    SUPPORTED_CITIES = {
        "london",
        "new york",
        "tokyo",
        "paris",
        "sydney",
        "berlin",
        "toronto",
        "singapore",
        "dubai",
        "mumbai",
        "los angeles",
        "chicago",
        "san francisco",
        "boston",
        "seattle",
        "austin",
        "denver",
        "miami",
        "atlanta",
    }

    # Weather conditions for realistic simulation
    WEATHER_CONDITIONS = [
        "Clear",
        "Partly Cloudy",
        "Cloudy",
        "Overcast",
        "Light Rain",
        "Rain",
        "Heavy Rain",
        "Thunderstorm",
        "Light Snow",
        "Snow",
        "Fog",
        "Windy",
    ]

    def run(self, arguments: dict[str, Any]) -> str:
        """
        Execute the mock weather lookup.

        Args:
            arguments: Dictionary containing:
                - city (str): The city name to query
                - units (str, optional): "metric" or "imperial", defaults to "metric"

        Returns:
            str: JSON-formatted string with weather data or error message

        Raises:
            No exceptions raised - all errors returned as formatted strings
        """
        logger.info(f"MockWeatherTool called with arguments: {arguments}")

        # Extract and validate parameters
        city = arguments.get("city", "").strip()
        units = arguments.get("units", "metric").lower()

        # Validate city parameter
        if not city:
            error_msg = "Error: City parameter is required and cannot be empty"
            logger.warning(error_msg)
            return json.dumps({"error": error_msg}, indent=2)

        # Validate units parameter
        if units not in ["metric", "imperial"]:
            error_msg = (
                f"Error: Invalid units '{units}'. Must be 'metric' or 'imperial'"
            )
            logger.warning(error_msg)
            return json.dumps({"error": error_msg}, indent=2)

        # Check if city is supported
        city_lower = city.lower()
        if city_lower not in self.SUPPORTED_CITIES:
            error_msg = f"Error: City '{city}' not found in database"
            logger.warning(f"{error_msg}. Requested: {city}")
            return json.dumps(
                {
                    "error": error_msg,
                    "suggestion": "Try cities like London, New York, Tokyo, Paris, or Sydney",
                },
                indent=2,
            )

        # Generate mock weather data
        weather_data = self._generate_mock_weather(city, units)
        logger.info(f"Generated mock weather for {city}: {weather_data['condition']}")

        return json.dumps(weather_data, indent=2)

    def _generate_mock_weather(self, city: str, units: str) -> dict[str, Any]:
        """
        Generate realistic mock weather data for a city.

        Args:
            city: City name
            units: Unit system ("metric" or "imperial")

        Returns:
            Dictionary with weather information
        """
        # Use city name as seed for consistent results per city
        random.seed(hash(city.lower()))

        # Generate temperature based on units
        if units == "metric":
            temperature = random.randint(-5, 35)
            temp_unit = "°C"
            wind_unit = "km/h"
            wind_speed = random.randint(5, 50)
        else:
            temperature = random.randint(23, 95)
            temp_unit = "°F"
            wind_unit = "mph"
            wind_speed = random.randint(3, 31)

        # Select random weather condition
        condition = random.choice(self.WEATHER_CONDITIONS)

        # Generate other weather parameters
        humidity = random.randint(30, 90)
        pressure = random.randint(980, 1030)

        return {
            "city": city.title(),
            "temperature": temperature,
            "unit": temp_unit,
            "condition": condition,
            "humidity": f"{humidity}%",
            "wind_speed": f"{wind_speed} {wind_unit}",
            "pressure": f"{pressure} hPa",
            "last_updated": "2024-01-15T12:00:00Z",
        }
