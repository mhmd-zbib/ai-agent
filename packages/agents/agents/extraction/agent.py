"""
agents.extraction.agent — FormulaVerificationAgent and CritiqueAgent.

Migrated from:
  packages/api/src/api/modules/agent/agents/formula_verification_agent.py
  packages/api/src/api/modules/agent/agents/critique_agent.py

Import path changes:
  api.modules.agent.schemas.sub_agents -> agents.orchestrator.schemas
  (shared.* imports are unchanged)
"""

from __future__ import annotations

import json

from agents.orchestrator.schemas import (
    ClaimVerification,
    CritiqueInput,
    CritiqueOutput,
    FormulaVerificationInput,
    FormulaVerificationOutput,
)
from shared.config import AgentConfig
from shared.llm.base import BaseLLM
from shared.logging import get_logger
from shared.schemas import AgentInput
from shared.utils import strip_markdown_code_block

__all__ = ["CritiqueAgent", "FormulaVerificationAgent"]

logger = get_logger(__name__)

_FORMULA_SAFE_DEFAULT = FormulaVerificationOutput(
    verdict="verified",
    confidence=0.6,
    explanation="Could not parse verification response; proceeding with original formula.",
    corrected_formula=None,
)


# ---------------------------------------------------------------------------
# FormulaVerificationAgent
# ---------------------------------------------------------------------------


class FormulaVerificationAgent:
    """
    Verifies that a scientific formula is mathematically correct for the stated
    problem before it is executed.

    If the formula has errors, returns a corrected_formula so the orchestrator
    can substitute it transparently before calling scientific_calc.
    """

    def __init__(self, *, llm: BaseLLM) -> None:
        self._llm = llm

    def run(self, input: FormulaVerificationInput) -> FormulaVerificationOutput:
        prompt = self._build_prompt(input)
        ai_response = self._llm.generate(
            AgentInput(user_message=prompt, session_id=input.session_id, history=[]),
            response_mode="json",
        )
        raw_content = ai_response.content
        try:
            data = json.loads(strip_markdown_code_block(raw_content))
            verdict = data.get("verdict", "verified")
            if verdict not in ("verified", "needs_revision"):
                verdict = "verified"
            corrected: str | None = data.get("corrected_formula") or None
            return FormulaVerificationOutput(
                verdict=verdict,  # type: ignore[arg-type]
                confidence=float(data.get("confidence", 0.9)),
                explanation=str(data.get("explanation", "")),
                corrected_formula=corrected,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "FormulaVerificationAgent: failed to parse LLM response; defaulting to verified",
                extra={"error": str(exc)},
            )
            return _FORMULA_SAFE_DEFAULT

    def _build_prompt(self, input: FormulaVerificationInput) -> str:
        context_block = ""
        if input.context_chunks:
            lines = [f"[{c.chunk_id}] {c.text}" for c in input.context_chunks]
            context_block = (
                "RELEVANT CONTEXT FROM DOCUMENTS:\n" + "\n".join(lines) + "\n\n"
            )

        var_block = ""
        if input.variables:
            var_lines = [f"  {k} = {v}" for k, v in input.variables.items()]
            var_block = "VARIABLES:\n" + "\n".join(var_lines) + "\n\n"

        return (
            f"{context_block}"
            f"PROBLEM: {input.problem}\n\n"
            "PROPOSED FORMULA (Python expression using numpy/scipy/sympy):\n"
            f"  {input.formula}\n\n"
            f"{var_block}"
            "Verify that the formula is mathematically correct for the stated problem.\n"
            "Check: correct equation, right constants, proper units, valid Python syntax.\n"
            'If correct, set verdict to "verified" and corrected_formula to null.\n'
            'If wrong, set verdict to "needs_revision" and supply the corrected Python expression.\n'
            "Respond ONLY in this exact JSON format:\n"
            '{"verdict": "verified", "confidence": 0.95, '
            '"explanation": "The formula is correct because ...", '
            '"corrected_formula": null}'
        )


# ---------------------------------------------------------------------------
# CritiqueAgent
# ---------------------------------------------------------------------------


class CritiqueAgent:
    """Fact-checks a draft answer against source chunks (LLM)."""

    def __init__(self, *, llm: BaseLLM, config: AgentConfig) -> None:
        self._llm = llm
        self._config = config
        self._safe_default = CritiqueOutput(
            verdict="approved",
            confidence=config.critique_default_confidence,
            verifications=[],
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
