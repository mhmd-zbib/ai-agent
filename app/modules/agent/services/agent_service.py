from typing import Literal

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput, AgentOutput, ToolCall
from app.modules.agent.services.tool_executor import ToolExecutor
from app.modules.tools.registry import ToolRegistry
from app.shared.logging import get_logger
from app.shared.schemas import AIResponse

logger = get_logger(__name__)


class AgentService:
    def __init__(
        self, 
        llm: BaseLLM, 
        tool_executor: ToolExecutor,
        tool_registry: ToolRegistry
    ) -> None:
        self._llm = llm
        self._tool_executor = tool_executor
        self._tool_registry = tool_registry

    def _build_tool_call(self, ai_response: AIResponse) -> ToolCall | None:
        if ai_response.tool_action is None:
            return None
        return ToolCall(
            name=ai_response.tool_action.tool_id,
            arguments=ai_response.tool_action.params,
        )

    def respond(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat"
    ) -> AgentOutput:
        """
        Generate a response using the LLM and execute any tool actions.
        
        The LLM returns an AIResponse in the new JSON format. This method
        converts it to the AgentOutput format for API compatibility.
        
        Args:
            payload: Agent input with user message and context
            response_mode: Response mode - "chat" for conversational, "tool_call" for structured JSON
        
        Returns:
            AgentOutput with message, tool calls, and tool results
        """
        logger.debug(
            "Generating agent response",
            extra={
                "session_id": payload.session_id,
                "response_mode": response_mode,
                "message_length": len(payload.user_message),
            }
        )
        
        # Get tools from registry for OpenAI native function calling
        tools = self._tool_registry.get_tools_for_openai()
        
        logger.debug(
            "Retrieved tools from registry",
            extra={
                "tool_count": len(tools),
                "tool_names": [t["function"]["name"] for t in tools],
            }
        )
        
        # Generate response from LLM with tools
        ai_response: AIResponse = self._llm.generate(
            payload, 
            response_mode=response_mode,
            tools=tools
        )
        
        logger.info(
            "Generated AI response",
            extra={
                "session_id": payload.session_id,
                "response_type": ai_response.type,
                "has_tool_action": ai_response.tool_action is not None,
            }
        )
        
        # Convert AIResponse to AgentOutput for backward compatibility
        tool_calls: list[ToolCall] = []
        tool_results = []

        tool_call = self._build_tool_call(ai_response)
        if tool_call is not None:
            logger.info(
                "Executing tool action",
                extra={
                    "session_id": payload.session_id,
                    "tool_id": tool_call.name,
                    "params": tool_call.arguments,
                }
            )
            tool_calls.append(tool_call)
            tool_results = self._tool_executor.run([tool_call])

            logger.info(
                "Tool execution completed",
                extra={
                    "session_id": payload.session_id,
                    "tool_id": tool_call.name,
                    "result_count": len(tool_results),
                }
            )

        logger.debug(
            "Agent response complete",
            extra={
                "session_id": payload.session_id,
                "message_length": len(ai_response.content),
                "tool_calls": len(tool_calls),
                "tool_results": len(tool_results),
            }
        )
        
        return AgentOutput(
            message=ai_response.content,
            tool_calls=tool_calls,
            tool_results=tool_results
        )
