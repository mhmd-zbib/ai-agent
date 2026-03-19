from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput, AgentOutput, ToolCall
from app.modules.agent.services.tool_executor import ToolExecutor
from app.shared.schemas import AIResponse


class AgentService:
    def __init__(self, llm: BaseLLM, tool_executor: ToolExecutor) -> None:
        self._llm = llm
        self._tool_executor = tool_executor

    def respond(self, payload: AgentInput) -> AgentOutput:
        """
        Generate a response using the LLM and execute any tool actions.
        
        The LLM returns an AIResponse in the new JSON format. This method
        converts it to the AgentOutput format for API compatibility.
        """
        ai_response: AIResponse = self._llm.generate(payload)
        
        # Convert AIResponse to AgentOutput for backward compatibility
        tool_calls = []
        tool_results = []
        
        # If the AI wants to execute a tool, create a ToolCall and execute it
        if ai_response.tool_action:
            tool_call = ToolCall(
                name=ai_response.tool_action.tool_id,
                arguments=ai_response.tool_action.params
            )
            tool_calls.append(tool_call)
            tool_results = self._tool_executor.run([tool_call])
        
        return AgentOutput(
            message=ai_response.content,
            tool_calls=tool_calls,
            tool_results=tool_results
        )

