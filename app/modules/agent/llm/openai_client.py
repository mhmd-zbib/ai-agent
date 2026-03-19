from __future__ import annotations

from openai import OpenAI

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput, AgentOutput
from app.shared.exceptions import ConfigurationError, UpstreamServiceError


class OpenAIClient(BaseLLM):
    def __init__(self, api_key: str | None, model: str, system_prompt: str) -> None:
        self._client = OpenAI(api_key=api_key) if api_key else None
        self._model = model
        self._system_prompt = system_prompt

    def generate(self, payload: AgentInput) -> AgentOutput:
        if self._client is None:
            raise ConfigurationError("OPENAI_API_KEY is required to use the chat endpoint.")

        input_messages = [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": self._system_prompt}],
            }
        ]
        input_messages.extend(
            {
                "role": item["role"],
                "content": [{"type": "input_text", "text": item["content"]}],
            }
            for item in payload.history
        )
        input_messages.append(
            {
                "role": "user",
                "content": [{"type": "input_text", "text": payload.user_message}],
            }
        )

        try:
            response = self._client.responses.create(model=self._model, input=input_messages)
            text = response.output_text or ""
            if not text.strip():
                raise UpstreamServiceError("OpenAI returned an empty response.")
            return AgentOutput(message=text)
        except UpstreamServiceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise UpstreamServiceError("Failed to generate a response from OpenAI.") from exc

