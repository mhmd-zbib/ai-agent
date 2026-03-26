"""
CritiqueAgent — fact-checks a draft answer against source chunks (LLM).
"""

from __future__ import annotations

import json

from app.modules.agent.schemas.sub_agents import (
    ClaimVerification,
    CritiqueInput,
    CritiqueOutput,
)
from app.shared.config import AgentConfig
from app.shared.llm.base import BaseLLM
from app.shared.logging import get_logger
from app.shared.schemas import AgentInput
from app.shared.utils import strip_markdown_code_block

logger = get_logger(__name__)


class CritiqueAgent:
    def __init__(self, *, llm: BaseLLM, config: AgentConfig) -> None:
        self._llm = llm
        self._config = config
        self._safe_default = CritiqueOutput(
            verdict="approved", confidence=config.critique_default_confidence, verifications=[]
        )

    def run(self, input: CritiqueInput) -> CritiqueOutput:
        prompt = self._build_prompt(input)
        ai_response = self._llm.generate(
            AgentInput(user_message=prompt, session_id=input.session_id, history=[]),
            response_mode="json",
        )
        raw_content = ai_response.content
        try:
            data = json.loads(strip_markdown_code_block(raw_content))
            verdict = data.get("verdict", "approved")
            if verdict not in ("approved", "needs_revision"):
                verdict = "approved"
            raw_verifications = data.get("verifications", [])
            verifications = [
                ClaimVerification(
                    claim=str(v.get("claim", "")),
                    supported=bool(v.get("supported", True)),
                    source_chunk_id=v.get("source_chunk_id"),
                    note=str(v.get("note", "")),
                )
                for v in raw_verifications
            ]
            return CritiqueOutput(
                verdict=verdict,  # type: ignore[arg-type]
                confidence=float(data.get("confidence", 0.9)),
                verifications=verifications,
                revision_instructions=str(data.get("revision_instructions", "")),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "CritiqueAgent: failed to parse LLM response; defaulting to approved",
                extra={"error": str(exc)},
            )
            return self._safe_default

    def _build_prompt(self, input: CritiqueInput) -> str:
        sources_block = ""
        if input.chunks:
            lines = [f"[{c.chunk_id}] {c.text}" for c in input.chunks]
            sources_block = "SOURCE CHUNKS:\n" + "\n".join(lines) + "\n\n"

        return (
            f"{sources_block}"
            f"QUESTION: {input.question}\n"
            f"DRAFT ANSWER: {input.draft_answer}\n\n"
            "Verify every claim in the draft answer against the source chunks.\n"
            "Respond ONLY in this exact JSON format:\n"
            '{"verdict": "approved", "confidence": 0.9, '
            '"verifications": [{"claim": "...", "supported": true, '
            '"source_chunk_id": "...", "note": ""}], '
            '"revision_instructions": ""}'
        )
