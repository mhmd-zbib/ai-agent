"""
agents.orchestrator.planner — PlanningService: generates execution plans for
multi-agent orchestration.

Migrated from packages/api/src/api/modules/agent/services/planning_service.py.
Import path changes:
  api.modules.agent.protocols -> agents.orchestrator.agent (IActionAgent defined locally)
  api.modules.agent.schemas.sub_agents -> agents.orchestrator.schemas
  (shared.* imports are unchanged)
"""

from __future__ import annotations

import json
from typing import Protocol

from .schemas import (
    AgentStep,
    OrchestratorInput,
    OrchestratorPlan,
)
from common.core.config import AgentConfig
from common.infra.llm.base import BaseLLM
from common.core.log_config import get_logger
from common.core.schemas import AgentInput
from common.core.utils import strip_markdown_code_block

__all__ = ["PlanningService"]

logger = get_logger(__name__)


class IActionAgent(Protocol):
    def list_tools(self) -> list[str]: ...


class PlanningService:
    """Generate execution plans via LLM."""

    def __init__(
        self,
        *,
        llm: BaseLLM,
        action_agent: IActionAgent,
        config: AgentConfig,
    ) -> None:
        self._llm = llm
        self._action_agent = action_agent
        self._config = config

    def create_plan(self, input: OrchestratorInput) -> OrchestratorPlan:
        """
        Generate an execution plan for the given input.

        Returns:
            OrchestratorPlan with steps and synthesis note
        """
        tools = self._action_agent.list_tools()
        history_lines = [
            f"{m['role']}: {m['content'][:200]}"
            for m in input.history[-self._config.orchestrator_history_window :]
        ]
        retrieval_note = self._build_retrieval_note(input.use_retrieval)

        prompt = self._build_planning_prompt(
            user_message=input.user_message,
            history_lines=history_lines,
            tools=tools,
            retrieval_note=retrieval_note,
        )

        try:
            return self._call_planning_llm(prompt, input)
        except Exception as exc:
            logger.warning(
                "Planning failed; using fallback plan",
                extra={"error": str(exc), "session_id": input.session_id},
            )
            return self._create_fallback_plan(input)

    def _build_retrieval_note(self, use_retrieval: bool) -> str:
        """Build retrieval context note for planning prompt."""
        if use_retrieval:
            return (
                "RETRIEVAL ENABLED — user has uploaded course documents. "
                "Use retrieval_agent + reasoning_agent for any question that may be answered "
                "from those documents. Only use action_agent tools (calculator, weather, etc.) "
                "for data that cannot come from documents (real-time data, computations)."
            )
        return "no retrieval"

    def _build_planning_prompt(
        self,
        user_message: str,
        history_lines: list[str],
        tools: list[str],
        retrieval_note: str,
    ) -> str:
        """Build the prompt for plan generation."""
        return (
            f"USER MESSAGE: {user_message}\n\n"
            f"SESSION HISTORY (last {len(history_lines)} turns):\n"
            + ("\n".join(history_lines) if history_lines else "(no history)")
            + f"\n\nAVAILABLE TOOLS: {', '.join(tools) if tools else 'none'}\n"
            f"RETRIEVAL: {retrieval_note}\n\n"
            "Produce an execution plan as JSON:\n"
            '{"steps": [{"agent": "...", "rationale": "...", "inputs": {}}], '
            '"final_synthesis_note": "..."}'
        )

    def _call_planning_llm(
        self, prompt: str, input: OrchestratorInput
    ) -> OrchestratorPlan:
        """Call LLM to generate plan and parse response."""
        ai_response = self._llm.generate(
            AgentInput(user_message=prompt, session_id=input.session_id, history=[]),
            response_mode="json",
        )
        raw = strip_markdown_code_block(ai_response.content)
        data = json.loads(raw)

        # Accept both "steps" and "agents" as the top-level key (model alias)
        raw_steps = data.get("steps") or data.get("agents") or []
        steps = [
            AgentStep(
                # Accept both "agent" and "name" as the agent identifier key
                agent=str(s.get("agent") or s.get("name") or ""),
                rationale=str(s.get("rationale", "")),
                inputs=s.get("inputs") or s.get("parameters") or {},
            )
            for s in raw_steps
            if s.get("agent") or s.get("name")
        ]

        # Enforce RAG core when retrieval is enabled
        steps = self._enforce_rag_core(steps, input.use_retrieval)

        return OrchestratorPlan(
            steps=steps,
            final_synthesis_note=str(data.get("final_synthesis_note", "")),
        )

    def _enforce_rag_core(
        self, steps: list[AgentStep], use_retrieval: bool
    ) -> list[AgentStep]:
        """
        Ensure retrieval_agent + reasoning_agent always run when retrieval is enabled.

        The planning LLM frequently drops one or both steps as history grows.
        Enforce them deterministically so retrieved context is always passed
        to the reasoning agent.
        """
        if not use_retrieval:
            return steps

        if not any(s.agent == "retrieval_agent" for s in steps):
            steps.insert(
                0,
                AgentStep(
                    agent="retrieval_agent",
                    rationale="Forced: retrieve relevant document chunks",
                    inputs={
                        "top_k": self._config.default_retrieval_top_k,
                        "strategy": "vector",
                    },
                ),
            )

        if not any(s.agent == "reasoning_agent" for s in steps):
            retrieval_idx = next(
                i for i, s in enumerate(steps) if s.agent == "retrieval_agent"
            )
            steps.insert(
                retrieval_idx + 1,
                AgentStep(
                    agent="reasoning_agent",
                    rationale="Forced: reason over retrieved chunks",
                    inputs={},
                ),
            )

        return steps

    def _create_fallback_plan(self, input: OrchestratorInput) -> OrchestratorPlan:
        """Create a safe fallback plan when LLM planning fails."""
        fallback_steps: list[AgentStep] = []

        if input.use_retrieval:
            fallback_steps.append(
                AgentStep(
                    agent="retrieval_agent",
                    rationale="fallback plan",
                    inputs={
                        "top_k": self._config.default_retrieval_top_k,
                        "strategy": "vector",
                    },
                )
            )

        fallback_steps.append(
            AgentStep(agent="reasoning_agent", rationale="fallback plan", inputs={})
        )

        return OrchestratorPlan(steps=fallback_steps, final_synthesis_note="")
