from __future__ import annotations

import json
from urllib import error, request

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput, AgentOutput
from app.shared.exceptions import UpstreamServiceError
from app.shared.logging import get_logger

logger = get_logger(__name__)


class OllamaClient(BaseLLM):
    def __init__(self, host: str, model: str, system_prompt: str) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._system_prompt = system_prompt
        logger.info(
            "OllamaClient initialized",
            extra={
                "host": self._host,
                "model": self._model,
            },
        )

    def generate(self, payload: AgentInput) -> AgentOutput:
        messages = [{"role": "system", "content": self._system_prompt}]
        messages.extend(
            {"role": item["role"], "content": item["content"]}
            for item in payload.history
        )
        messages.append({"role": "user", "content": payload.user_message})

        request_payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }

        http_request = request.Request(
            url=f"{self._host}/api/chat",
            data=json.dumps(request_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        logger.debug(
            "Sending request to Ollama",
            extra={
                "host": self._host,
                "model": self._model,
                "message_count": len(messages),
            },
        )

        try:
            with request.urlopen(http_request, timeout=60) as response:  # noqa: S310
                raw_response = response.read().decode("utf-8")
        except error.URLError as exc:
            logger.error(
                "Failed to reach Ollama host",
                extra={
                    "host": self._host,
                    "error": str(exc),
                },
                exc_info=True,
            )
            raise UpstreamServiceError(
                f"Failed to reach Ollama at {self._host}. Please ensure Ollama is running."
            ) from exc
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to generate response from Ollama",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
            raise UpstreamServiceError(
                "Failed to generate a response from Ollama. Please try again."
            ) from exc

        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            logger.error(
                "Ollama returned invalid JSON",
                extra={
                    "raw_response": raw_response[:500],  # Log first 500 chars
                },
                exc_info=True,
            )
            raise UpstreamServiceError(
                "Ollama returned an invalid JSON response."
            ) from exc

        text = str(parsed.get("message", {}).get("content", "")).strip()
        if not text:
            logger.warning(
                "Ollama returned empty response",
                extra={
                    "parsed_response": parsed,
                },
            )
            raise UpstreamServiceError("Ollama returned an empty response.")

        logger.info(
            "Successfully generated response from Ollama",
            extra={
                "response_length": len(text),
            },
        )

        return AgentOutput(message=text)

