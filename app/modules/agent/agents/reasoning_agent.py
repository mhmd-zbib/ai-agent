"""
ReasoningAgent — step-by-step reasoning over retrieved context (LLM).
"""
from __future__ import annotations

import json

from app.modules.agent.schemas.sub_agents import (
    ReasoningInput,
    ReasoningOutput,
    ReasoningStep,
)
from app.shared.llm.base import BaseLLM
from app.shared.logging import get_logger
from app.shared.schemas import AgentInput

logger = get_logger(__name__)


class ReasoningAgent:
    def __init__(self, *, llm: BaseLLM) -> None:
        self._llm = llm

    def run(self, input: ReasoningInput) -> ReasoningOutput:
        prompt = self._build_prompt(input)
        ai_response = self._llm.generate(
            AgentInput(user_message=prompt, session_id=input.session_id, history=[])
        )
        raw_content = ai_response.content
        try:
            data = json.loads(self._strip_code_block(raw_content))
            raw_steps = data.get("steps", [])
            steps = [
                ReasoningStep(
                    step_number=int(s.get("step_number", i + 1)),
                    reasoning=str(s.get("reasoning", "")),
                )
                for i, s in enumerate(raw_steps)
            ]
            adequacy = data.get("context_adequacy", "sufficient")
            if adequacy not in ("sufficient", "insufficient"):
                adequacy = "sufficient"
            return ReasoningOutput(
                answer=str(data.get("answer", "")),
                steps=steps,
                context_adequacy=adequacy,  # type: ignore[arg-type]
                confidence=float(data.get("confidence", 0.9)),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "ReasoningAgent: failed to parse LLM response; using fallback",
                extra={"error": str(exc)},
            )
            return ReasoningOutput(
                answer=raw_content,
                steps=[],
                context_adequacy="insufficient",
                confidence=0.5,
            )

    def _build_prompt(self, input: ReasoningInput) -> str:
        context_block = ""
        if input.chunks:
            lines = [f"[{c.chunk_id}] {c.text}" for c in input.chunks]
            context_block = "CONTEXT:\n" + "\n".join(lines) + "\n\n"

        return (
            f"{context_block}"
            f"QUESTION: {input.question}\n\n"
            "Respond ONLY in this exact JSON format:\n"
            '{"answer": "...", "steps": [{"step_number": 1, "reasoning": "..."}], '
            '"context_adequacy": "sufficient", "confidence": 0.9}'
        )

    def _strip_code_block(self, content: str) -> str:
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        return content
