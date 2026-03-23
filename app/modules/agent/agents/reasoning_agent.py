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
            AgentInput(user_message=prompt, session_id=input.session_id, history=[]),
            response_mode="json",
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

        history_block = ""
        if input.history:
            lines = [f"{m['role']}: {m['content'][:300]}" for m in input.history[-6:]]
            history_block = "CONVERSATION HISTORY:\n" + "\n".join(lines) + "\n\n"

        no_context_instruction = (
            "NO CONTEXT WAS PROVIDED. You MUST set context_adequacy to "
            '"insufficient" and answer with exactly: '
            '"I cannot answer this question because no relevant document context was found." '
            "Do NOT use your training knowledge.\n\n"
            if not input.chunks
            else ""
        )

        return (
            f"{context_block}"
            f"{history_block}"
            f"QUESTION: {input.question}\n\n"
            f"{no_context_instruction}"
            "STRICT RULES:\n"
            "1. Answer ONLY from the CONTEXT above. Do NOT use your training knowledge.\n"
            "2. If the context does not contain enough information to answer, set "
            'context_adequacy to "insufficient".\n'
            "3. Never invent facts, courses, topics, or details not present in the context.\n"
            "4. Resolve pronouns/references using CONVERSATION HISTORY only.\n\n"
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
