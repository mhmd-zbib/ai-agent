from __future__ import annotations

import json

from openai import OpenAI
from pydantic import ValidationError

from app.modules.agent.llm.base import BaseLLM
from app.modules.agent.schemas import AgentInput
from app.shared.exceptions import UpstreamServiceError
from app.shared.logging import get_logger
from app.shared.schemas import AIResponse

logger = get_logger(__name__)


class OllamaClient(BaseLLM):
    def __init__(self, host: str, model: str, system_prompt: str) -> None:
        # Ensure host ends with /v1 for OpenAI-compatible endpoint
        base_url = host.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        
        # Initialize OpenAI client with Ollama endpoint
        self._client = OpenAI(
            api_key="ollama",  # Ollama doesn't require real API key
            base_url=base_url
        )
        self._model = model
        self._system_prompt = system_prompt
        
        logger.info(
            "OllamaClient initialized with OpenAI SDK",
            extra={
                "base_url": base_url,
                "model": self._model,
            },
        )

    def generate(self, payload: AgentInput) -> AIResponse:
        # Build message array (same as OpenAI client)
        messages = [{"role": "system", "content": self._system_prompt}]
        messages.extend(
            {"role": item["role"], "content": item["content"]}
            for item in payload.history
        )
        messages.append({"role": "user", "content": payload.user_message})

        logger.debug(
            "Sending request to Ollama via OpenAI SDK",
            extra={
                "model": self._model,
                "message_count": len(messages),
            },
        )

        try:
            # Use OpenAI SDK with JSON mode
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"}
            )
            
            # Extract content
            ai_content = response.choices[0].message.content or ""
            
            logger.debug(
                "Received response from Ollama",
                extra={
                    "content_length": len(ai_content),
                }
            )
            
            # Parse and validate AIResponse
            ai_response_data = json.loads(ai_content)
            return AIResponse(**ai_response_data)
            
        except ValidationError as e:
            logger.error(
                "Invalid AIResponse schema from Ollama",
                extra={"validation_error": str(e)},
            )
            raise UpstreamServiceError(
                f"Ollama returned invalid response format: {e}"
            ) from e
        except json.JSONDecodeError as e:
            logger.error(
                "Invalid JSON from Ollama",
                extra={"json_error": str(e), "content": ai_content[:200]},
            )
            raise UpstreamServiceError(
                f"Ollama returned invalid JSON: {e}"
            ) from e
        except Exception as e:
            logger.error(
                "Error calling Ollama via OpenAI SDK",
                extra={"error": str(e)},
            )
            raise UpstreamServiceError(
                f"Failed to generate response from Ollama: {e}"
            ) from e

