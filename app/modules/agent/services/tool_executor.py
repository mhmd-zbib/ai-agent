from app.modules.agent.schemas import ToolCall, ToolResult
from app.modules.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def run(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        results: list[ToolResult] = []
        for call in tool_calls:
            tool = self._registry.resolve(call.name)
            output = tool.run(call.arguments)
            results.append(ToolResult(name=call.name, output=output))
        return results

