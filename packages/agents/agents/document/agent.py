"""
agents.document.agent — ActionAgent: executes registered tools (no LLM).

Migrated from packages/api/src/api/modules/agent/agents/action_agent.py.
Import path changes:
  api.modules.agent.schemas.sub_agents -> agents.orchestrator.schemas
  api.modules.tools.exceptions         -> agents.core.tool
  (shared.* imports are unchanged)
"""

from __future__ import annotations

from agents.core.tool import (
    ToolConfigurationError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolValidationError,
)
from agents.orchestrator.schemas import ActionInput, ActionOutput
from shared.logging import get_logger
from shared.protocols import IToolRegistry

__all__ = ["ActionAgent"]

logger = get_logger(__name__)


class ActionAgent:
    """Executes tools from the tool registry without an LLM call."""

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
        except ToolNotFoundError as e:
            logger.warning(
                "ActionAgent: tool not found",
                extra={"tool_id": e.tool_id, "session_id": input.session_id},
            )
            return ActionOutput(
                tool_id=input.tool_id,
                result="",
                succeeded=False,
                error_message=f"I don't have access to the '{e.tool_id}' tool.",
            )
        except ToolExecutionError as e:
            logger.error(
                "ActionAgent: tool execution failed",
                extra={
                    "tool_id": e.tool_id,
                    "session_id": input.session_id,
                    "reason": e.reason,
                },
            )
            return ActionOutput(
                tool_id=input.tool_id,
                result="",
                succeeded=False,
                error_message=e.user_message,
            )
        except ToolConfigurationError as e:
            logger.error(
                "ActionAgent: tool misconfigured",
                extra={
                    "tool_id": e.tool_id,
                    "session_id": input.session_id,
                    "issue": e.issue,
                },
            )
            return ActionOutput(
                tool_id=input.tool_id,
                result="",
                succeeded=False,
                error_message=f"The {e.tool_id} tool is not properly configured.",
            )
        except ToolValidationError as e:
            logger.warning(
                "ActionAgent: tool validation failed",
                extra={
                    "tool_id": e.tool_id,
                    "session_id": input.session_id,
                    "errors": e.validation_errors,
                },
            )
            return ActionOutput(
                tool_id=input.tool_id,
                result="",
                succeeded=False,
                error_message=f"Invalid input: {', '.join(e.validation_errors)}",
            )
        except Exception as exc:
            logger.exception(
                "ActionAgent: unexpected tool error",
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
                error_message="An unexpected error occurred while using the tool.",
            )
