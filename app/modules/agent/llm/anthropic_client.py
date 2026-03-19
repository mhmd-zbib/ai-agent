from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput, AgentOutput
from app.shared.exceptions import UpstreamServiceError


class AnthropicClient(BaseLLM):
    def generate(self, payload: AgentInput) -> AgentOutput:  # noqa: ARG002
        raise UpstreamServiceError("Anthropic client is not configured yet.")

