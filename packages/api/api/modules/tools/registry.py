from typing import Any

from api.modules.tools.base import BaseTool
from api.modules.tools.exceptions import ToolNotFoundError


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        name = tool.name.strip()
        if not name:
            raise ValueError("Tool name cannot be empty")
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = tool

    def resolve(self, name: str) -> BaseTool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(name)
        return tool

    def list_tools(self) -> list[str]:
        """Return registered tool names in stable registration order."""
        return list(self._tools.keys())

    def get_tools_for_openai(self) -> list[dict[str, Any]]:
        """Get all registered tools in OpenAI function calling format.

        Returns list like:
        [
            {
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": "Perform mathematical calculations",
                    "parameters": {...}
                }
            },
            ...
        ]
        """
        return [tool.to_openai_tool() for tool in self._tools.values()]
