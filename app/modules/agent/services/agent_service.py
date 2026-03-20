from typing import Literal, Optional

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
        tool_calls = []
        tool_results = []
        
        # If the AI wants to execute a tool, create a ToolCall and execute it
        if ai_response.tool_action:
            logger.info(
                "Executing tool action",
                extra={
                    "session_id": payload.session_id,
                    "tool_id": ai_response.tool_action.tool_id,
                    "params": ai_response.tool_action.params,
                }
            )
            
            try:
                tool_call = ToolCall(
                    name=ai_response.tool_action.tool_id,
                    arguments=ai_response.tool_action.params
                )
                tool_calls.append(tool_call)
                
                # Execute the tool
                tool_results = self._tool_executor.run([tool_call])
                
                logger.info(
                    "Tool execution completed",
                    extra={
                        "session_id": payload.session_id,
                        "tool_id": ai_response.tool_action.tool_id,
                        "result_count": len(tool_results),
                    }
                )
            except KeyError as e:
                logger.error(
                    "Tool not found",
                    extra={
                        "session_id": payload.session_id,
                        "tool_id": ai_response.tool_action.tool_id,
                        "error": str(e),
                    }
                )
                # Return error as tool result
                from app.modules.agent.schemas import ToolResult
                tool_results = [
                    ToolResult(
                        name=ai_response.tool_action.tool_id,
                        output=f"Error: Tool '{ai_response.tool_action.tool_id}' not found"
                    )
                ]
            except Exception as e:
                logger.error(
                    "Tool execution failed",
                    extra={
                        "session_id": payload.session_id,
                        "tool_id": ai_response.tool_action.tool_id,
                        "error": str(e),
                    }
                )
                # Return error as tool result
                from app.modules.agent.schemas import ToolResult
                tool_results = [
                    ToolResult(
                        name=ai_response.tool_action.tool_id,
                        output=f"Error executing tool: {str(e)}"
                    )
                ]
        
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

