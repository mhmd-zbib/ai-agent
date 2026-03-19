from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput, AgentOutput
from app.modules.agent.services.tool_executor import ToolExecutor


class AgentService:
    def __init__(self, llm: BaseLLM, tool_executor: ToolExecutor) -> None:
        self._llm = llm
        self._tool_executor = tool_executor

    def respond(self, payload: AgentInput) -> AgentOutput:
        output = self._llm.generate(payload)
        if output.tool_calls:
            output.tool_results = self._tool_executor.run(output.tool_calls)
        return output

