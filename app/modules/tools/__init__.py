"""
Tool registry initialization and configuration.

This module provides the central registry for all agent tools. Tools are
divided into production tools (always available) and demo tools (optional,
enabled via ENABLE_DEMO_TOOLS environment variable).

Demo tools are intended for development, testing, and demonstration purposes.
They showcase different tool patterns, parameter types, and error handling
strategies without requiring external services or credentials.
"""

from app.modules.tools.implementations import (
    CalculatorTool,
    DateTimeNowTool,
    DocumentLookupTool,
    WeatherTool,
    WebSearchTool,
)
from app.modules.tools.registry import ToolRegistry
from app.shared.config import get_settings


def get_tool_registry() -> ToolRegistry:
    """
    Create and populate the tool registry.

    Production tools are always registered. Demo/showcase tools are
    conditionally registered based on the ENABLE_DEMO_TOOLS environment
    variable setting.

    Returns:
        ToolRegistry: Configured registry with all enabled tools
    """
    registry = ToolRegistry()

    # Always register production tools
    registry.register(CalculatorTool())
    registry.register(DateTimeNowTool())
    registry.register(WebSearchTool())
    registry.register(WeatherTool())
    registry.register(DocumentLookupTool())

    # Conditionally register demo tools for development/testing
    settings = get_settings()
    if settings.enable_demo_tools:
        try:
            from app.modules.tools.implementations.showcase import (
                MockAPITool,
                MockDatabaseTool,
                MockWeatherTool,
            )

            registry.register(MockWeatherTool())
            registry.register(MockDatabaseTool())
            registry.register(MockAPITool())
        except ImportError:
            # Demo tools not yet implemented - this is expected until
            # the showcase module is created (see TODO: demo-tools-showcase)
            pass

    return registry


__all__ = ["get_tool_registry", "ToolRegistry"]
