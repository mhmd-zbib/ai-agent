"""
ActionAgent — executes registered tools (no LLM).
"""

from __future__ import annotations

from app.modules.agent.schemas.sub_agents import ActionInput, ActionOutput
from app.shared.logging import get_logger
from app.shared.protocols import IToolRegistry

logger = get_logger(__name__)


class ActionAgent:
    def __init__(self, *, tool_registry: IToolRegistry) -> None:
        self._tool_registry = tool_registry

    def list_tools(self) -> list[str]:
        return self._tool_registry.list_tools()

    def run(self, input: ActionInput) -> ActionOutput:
        params: dict[str, object] = dict(input.tool_params)
        if input.user_id:
            params["user_id"] = input.user_id

        logger.info(
            "ActionAgent: executing tool",
            extra={
                "tool_id": input.tool_id,
                "session_id": input.session_id,
                "params_keys": list(params.keys()),
            },
        )

        try:
            tool = self._tool_registry.resolve(input.tool_id)
            result = tool.run(params)
            logger.info(
                "ActionAgent: tool execution completed",
                extra={"tool_id": input.tool_id, "result_length": len(result)},
            )
            return ActionOutput(tool_id=input.tool_id, result=result, succeeded=True)
        except KeyError:
            logger.error(
                "ActionAgent: tool not registered",
                extra={"tool_id": input.tool_id, "session_id": input.session_id},
            )
            return ActionOutput(
                tool_id=input.tool_id,
                result="",
                succeeded=False,
                error_message=f"Tool '{input.tool_id}' is not registered.",
            )
        except Exception as exc:
            logger.error(
                "ActionAgent: tool execution failed",
                extra={
                    "tool_id": input.tool_id,
                    "session_id": input.session_id,
                    "error": str(exc),
                },
            )
            return ActionOutput(
                tool_id=input.tool_id,
                result="",
                succeeded=False,
                error_message=f"Tool '{input.tool_id}' raised: {exc}",
            )
