"""
FormulaVerificationAgent — uses the LLM to verify a scientific formula is
mathematically correct for the stated problem before it is executed.

If the formula has errors the agent returns a corrected_formula so the
orchestrator can substitute it transparently before calling scientific_calc.
"""

from __future__ import annotations

import json

from app.modules.agent.schemas.sub_agents import (
    FormulaVerificationInput,
    FormulaVerificationOutput,
)
from app.shared.llm.base import BaseLLM
from app.shared.logging import get_logger
from app.shared.schemas import AgentInput
from app.shared.utils import strip_markdown_code_block

logger = get_logger(__name__)

_SAFE_DEFAULT = FormulaVerificationOutput(
    verdict="verified",
    confidence=0.6,
    explanation="Could not parse verification response; proceeding with original formula.",
    corrected_formula=None,
)


class FormulaVerificationAgent:
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
            return _SAFE_DEFAULT

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
            f"PROPOSED FORMULA (Python expression using numpy/scipy/sympy):\n"
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
