from typing import Any, Literal, Optional

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput
from app.shared.exceptions import UpstreamServiceError
from app.shared.schemas import AIResponse


class AnthropicClient(BaseLLM):
    def generate(
        self,
        payload: AgentInput,
        response_mode: Literal["chat", "tool_call"] = "chat",
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> AIResponse:  # noqa: ARG002
        raise UpstreamServiceError("Anthropic client is not configured yet.")
