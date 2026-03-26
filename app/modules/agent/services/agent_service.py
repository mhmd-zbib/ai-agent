from __future__ import annotations

from typing import Literal

from app.modules.tools.exceptions import (
    ToolConfigurationError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolValidationError,
)
from app.shared.llm.base import BaseLLM
from app.shared.logging import get_logger
from app.shared.protocols import IToolRegistry
from app.shared.schemas import AgentInput, AIResponse

logger = get_logger(__name__)


class AgentService:
    """
    Owns the LLM invocation / tool-execution / follow-up synthesis cycle.

    Responsibilities:
    - Call the LLM with the user's agent input and available tools
    - Execute any requested tool action via the tool registry
    - Optionally run a follow-up LLM call to synthesize tool results into prose
    - Return a finalised AIResponse (type="text", tool_action cleared)
    """

    def __init__(self, *, llm: BaseLLM, tool_registry: IToolRegistry) -> None:
        self._llm = llm
        self._tool_registry = tool_registry

    def run(self, agent_input: AgentInput, user_id: str = "") -> AIResponse:
        """Run one agent turn: LLM → optional tool → optional follow-up → finalize."""
        response_mode: Literal["chat", "tool_call"] = self._resolve_response_mode()
        tools = self._tool_registry.get_tools_for_openai()

        logger.debug(
            "Generating response",
            extra={
                "session_id": agent_input.session_id,
                "response_mode": response_mode,
                "tool_count": len(tools),
            },
        )

        ai_response = self._llm.generate(
            agent_input, response_mode=response_mode, tools=tools
        )

        logger.info(
            "Generated AI response",
            extra={
                "session_id": agent_input.session_id,
                "response_type": ai_response.type,
                "response_mode": response_mode,
                "has_tool_action": ai_response.tool_action is not None,
                "confidence": ai_response.metadata.confidence
                if ai_response.metadata
                else None,
            },
        )

        had_tool_action = ai_response.tool_action is not None
        ai_response, tool_succeeded = self._execute_tool_action(
            agent_input.session_id, ai_response, user_id
        )

        if had_tool_action and tool_succeeded:
            try:
                ai_response.content = self._synthesize_followup(
                    agent_input, ai_response.content
                )
            except Exception as exc:
                logger.warning(
                    "Follow-up synthesis failed; falling back to tool response",
                    extra={"session_id": agent_input.session_id, "error": str(exc)},
                )

        return self._finalize(ai_response)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_response_mode(self) -> Literal["chat", "tool_call"]:
        return "chat"

    def _format_user_content(
        self, ai_response: AIResponse, tool_result: str | None = None
    ) -> str:
        if tool_result is None:
            return ai_response.content

        if ai_response.type == "tool":
            return tool_result

        if ai_response.type == "mixed":
            base = ai_response.content.strip()
            return f"{base}\n\n{tool_result}" if base else tool_result

        return ai_response.content

    def _execute_tool_action(
        self, session_id: str, ai_response: AIResponse, user_id: str = ""
    ) -> tuple[AIResponse, bool]:
        """Execute the requested tool and return (updated_response, succeeded).

        Returns succeeded=False when the tool is missing or raises, so the
        caller can skip followup synthesis (the error message is already
        user-friendly).
        """
        if ai_response.tool_action is None:
            return ai_response, False

        if user_id:
            ai_response.tool_action.params["user_id"] = user_id

        logger.info(
            "Tool action detected - executing",
            extra={
                "session_id": session_id,
                "tool_id": ai_response.tool_action.tool_id,
                "params": ai_response.tool_action.params,
            },
        )

        try:
            tool = self._tool_registry.resolve(ai_response.tool_action.tool_id)
            tool_result = tool.run(ai_response.tool_action.params)
            logger.info(
                "Tool execution completed",
                extra={
                    "session_id": session_id,
                    "tool_id": ai_response.tool_action.tool_id,
                    "result_length": len(tool_result),
                },
            )
            ai_response.content = self._format_user_content(ai_response, tool_result)
            return ai_response, True
        except ToolNotFoundError as e:
            logger.warning("Tool not found", extra={"tool_id": e.tool_id})
            ai_response.content = f"I don't have access to the '{e.tool_id}' tool."
            return ai_response, False
        except ToolExecutionError as e:
            logger.error(
                "Tool execution failed",
                extra={"tool_id": e.tool_id, "reason": e.reason},
            )
            ai_response.content = e.user_message
            return ai_response, False
        except ToolConfigurationError as e:
            logger.error(
                "Tool misconfigured",
                extra={"tool_id": e.tool_id, "issue": e.issue},
            )
            ai_response.content = f"The {e.tool_id} tool is not properly configured."
            return ai_response, False
        except ToolValidationError as e:
            logger.warning(
                "Tool validation failed",
                extra={"tool_id": e.tool_id, "errors": e.validation_errors},
            )
            ai_response.content = f"Invalid input: {', '.join(e.validation_errors)}"
            return ai_response, False
        except Exception as e:
            logger.exception("Unexpected tool error")
            ai_response.content = "An unexpected error occurred while using the tool."
            return ai_response, False

    def _synthesize_followup(
        self, agent_input: AgentInput, tool_observation: str
    ) -> str:
        """Ask the LLM to synthesize a final prose answer from tool results."""
        followup_history = list(agent_input.history)
        followup_history.append({"role": "user", "content": agent_input.user_message})
        followup_history.append(
            {
                "role": "assistant",
                "content": (
                    "Tool observation:\n"
                    f"{tool_observation}\n\n"
                    "Now answer the user's full question in natural conversational text. "
                    "Do not output JSON."
                ),
            }
        )
        followup_input = AgentInput(
            user_message="Please provide the final user-facing answer.",
            session_id=agent_input.session_id,
            history=followup_history,
        )
        followup_response = self._llm.generate(
            followup_input, response_mode="chat", tools=[]
        )
        return followup_response.content.strip() or tool_observation

    def _finalize(self, ai_response: AIResponse) -> AIResponse:
        """Ensure chat mode returns conversational text instead of tool envelope."""
        ai_response.type = "text"
        ai_response.tool_action = None
        return ai_response
