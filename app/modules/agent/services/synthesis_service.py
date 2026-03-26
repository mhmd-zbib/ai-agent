"""
SynthesisService — combines agent outputs into final user-facing answers.

Responsibility: Take outputs from various agents (reasoning, action, critique)
and synthesize them into a coherent, natural response using an LLM.
"""

from __future__ import annotations

from app.modules.agent.schemas.sub_agents import (
    ActionOutput,
    CritiqueOutput,
    OrchestratorInput,
    ReasoningOutput,
)
from app.shared.llm.base import BaseLLM
from app.shared.logging import get_logger
from app.shared.schemas import AgentInput

logger = get_logger(__name__)


class SynthesisService:
    """Synthesize agent outputs into final answers."""

    def __init__(self, *, synthesis_llm: BaseLLM) -> None:
        self._synthesis_llm = synthesis_llm

    def synthesize(
        self,
        input: OrchestratorInput,
        action_output: ActionOutput | None,
        reasoning_output: ReasoningOutput | None,
        critique_output: CritiqueOutput | None,
    ) -> str:
        """
        Synthesize final answer from agent outputs.

        Priority order:
        1. Document-grounded answers (reasoning with sufficient context)
        2. Tool results (action agent outputs)
        3. Conversational answers (reasoning without retrieval)
        4. Fallback messages

        Args:
            input: Original orchestrator input
            action_output: Output from action agent (if ran)
            reasoning_output: Output from reasoning agent (if ran)
            critique_output: Output from critique agent (if ran)

        Returns:
            Final synthesized answer string
        """
        # Document-grounded answers take priority when the reasoning agent found
        # sufficient context. Action-agent tool results (web_search, weather…)
        # are only used when documents could NOT answer the question.
        if (
            reasoning_output is not None
            and reasoning_output.context_adequacy == "sufficient"
        ):
            return self._synthesize_reasoning_output(
                input, reasoning_output, critique_output
            )

        # Tool result available (action_agent ran successfully).
        if action_output is not None and action_output.succeeded:
            return self._synthesize_action_output(input, action_output)

        # Reasoning ran but context was insufficient — do NOT hallucinate.
        # Return a clear "no information" message so the user knows to upload docs.
        if reasoning_output is not None and input.use_retrieval:
            return self._no_information_message(input.user_message)

        # Reasoning ran without retrieval (conversational mode) — rephrase safely.
        if reasoning_output is not None:
            return self._synthesize_conversational(input, reasoning_output)

        # No reasoning or tool output at all.
        if input.use_retrieval:
            return self._no_information_message(input.user_message)

        return "I'm sorry, I was unable to process your request. Please try again."

    def _synthesize_reasoning_output(
        self,
        input: OrchestratorInput,
        reasoning_output: ReasoningOutput,
        critique_output: CritiqueOutput | None,
    ) -> str:
        """Synthesize reasoning output, applying critique if needed."""
        if critique_output is not None and critique_output.verdict == "needs_revision":
            prompt = (
                f"Original question: {input.user_message}\n"
                f"Draft answer: {reasoning_output.answer}\n"
                f"Revision instructions: {critique_output.revision_instructions}\n\n"
                "Provide a revised, accurate answer incorporating the revision instructions. "
                "Only use information from the draft answer — do not add outside knowledge."
            )
        else:
            prompt = (
                f"Original question: {input.user_message}\n"
                f"Answer: {reasoning_output.answer}\n\n"
                "Restate this answer in a natural, conversational way. "
                "Do NOT add any information beyond what is in the Answer above."
            )

        return self._call_synthesis_llm(prompt, input.session_id)

    def _synthesize_action_output(
        self, input: OrchestratorInput, action_output: ActionOutput
    ) -> str:
        """Synthesize tool/action output into natural response."""
        prompt = (
            f"Original question: {input.user_message}\n"
            f"Tool '{action_output.tool_id}' returned: {action_output.result}\n\n"
            "Provide a natural, conversational answer using this tool result. "
            "Do NOT add any information beyond what the tool returned."
        )
        return self._call_synthesis_llm(prompt, input.session_id)

    def _synthesize_conversational(
        self, input: OrchestratorInput, reasoning_output: ReasoningOutput
    ) -> str:
        """Synthesize conversational response (no retrieval context)."""
        prompt = (
            f"Original question: {input.user_message}\n"
            f"Answer: {reasoning_output.answer}\n\n"
            "Restate this answer in a natural, conversational way. "
            "Do NOT add any information beyond what is in the Answer above."
        )
        return self._call_synthesis_llm(prompt, input.session_id)

    def _no_information_message(self, user_message: str) -> str:
        """Return a clear message when no relevant information is found."""
        return (
            "I could not find relevant information in your uploaded documents "
            f'to answer: "{user_message}". '
            "Please make sure the relevant document has been uploaded and processed."
        )

    def _call_synthesis_llm(self, prompt: str, session_id: str) -> str:
        """Call synthesis LLM with error handling."""
        try:
            ai_response = self._synthesis_llm.generate(
                AgentInput(user_message=prompt, session_id=session_id, history=[])
            )
            return ai_response.content.strip() or prompt
        except Exception as exc:
            logger.warning(
                "Synthesis LLM call failed",
                error=str(exc),
                session_id=session_id,
            )
            return prompt
