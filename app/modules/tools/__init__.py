from app.modules.tools.implementations import CalculatorTool, DocumentLookupTool, WebSearchTool
from app.modules.tools.registry import ToolRegistry


def get_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(WebSearchTool())
    registry.register(DocumentLookupTool())
    return registry


__all__ = ["get_tool_registry", "ToolRegistry"]

