from typing import Any

from app.modules.tools.base import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def resolve(self, name: str) -> BaseTool:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' is not registered")
        return tool

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

