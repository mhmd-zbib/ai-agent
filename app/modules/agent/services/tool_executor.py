from app.modules.agent.schemas import ToolCall, ToolResult
from app.shared.logging import get_logger
from app.shared.protocols import IToolRegistry

logger = get_logger(__name__)


class ToolExecutor:
    def __init__(self, registry: IToolRegistry) -> None:
        self._registry = registry

    def _run_single(self, call: ToolCall) -> ToolResult:
        try:
            tool = self._registry.resolve(call.name)
            output = tool.run(call.arguments)
            return ToolResult(name=call.name, output=output)
        except KeyError:
            logger.warning("Tool not found during execution", extra={"tool_name": call.name})
            return ToolResult(name=call.name, output=f"Error: Tool '{call.name}' not found")
        except Exception as exc:
            logger.error(
                "Tool execution failed",
                extra={"tool_name": call.name, "error": str(exc)},
            )
            return ToolResult(name=call.name, output="Error: Tool execution failed")

    def run(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        return [self._run_single(call) for call in tool_calls]
