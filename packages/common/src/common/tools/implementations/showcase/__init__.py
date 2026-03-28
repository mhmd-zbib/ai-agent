"""
Showcase Demo Tools - Educational examples demonstrating BaseTool patterns.

This module contains three demo tools that showcase different patterns:
- MockWeatherTool: String parameters, enum validation, simple JSON responses
- MockDatabaseTool: Multiple parameter types, SQL injection prevention, pagination
- MockAPITool: Object parameters, HTTP methods, error states, retry logic

These tools are designed for education and testing purposes.
"""

from .showcase.mock_api import MockAPITool
from .showcase.mock_database import MockDatabaseTool
from .showcase.mock_weather import MockWeatherTool

__all__ = [
    "MockWeatherTool",
    "MockDatabaseTool",
    "MockAPITool",
]
