"""
OrchestratorService — plans and delegates to focused sub-agents.
"""
from __future__ import annotations

import json

from app.modules.agent.protocols import (
    IActionAgent,
    ICritiqueAgent,
    IMemoryAgent,
    IReasoningAgent,
    IRetrievalAgent,
)
from app.modules.agent.schemas.sub_agents import (
    ActionInput,
    ActionOutput,
    AgentStep,
    CritiqueInput,
    CritiqueOutput,
    MemoryInput,
    OrchestratorInput,
    OrchestratorOutput,
    OrchestratorPlan,
    ReasoningInput,
    ReasoningOutput,
    RetrievalInput,
)
from app.shared.llm.base import BaseLLM
from app.shared.logging import get_logger
from app.shared.schemas import AgentInput

logger = get_logger(__name__)


class OrchestratorService:
    def __init__(
        self,
        *,
        llm: BaseLLM,
        retrieval_agent: IRetrievalAgent,
        reasoning_agent: IReasoningAgent,
        critique_agent: ICritiqueAgent,
        memory_agent: IMemoryAgent,
        action_agent: IActionAgent,
    ) -> None:
        self._llm = llm
        self._retrieval_agent = retrieval_agent
        self._reasoning_agent = reasoning_agent
        self._critique_agent = critique_agent
        self._memory_agent = memory_agent
        self._action_agent = action_agent

    def run(self, input: OrchestratorInput) -> OrchestratorOutput:
        plan = self._plan(input)

        agent_trace: list[dict[str, object]] = []
        retrieval_output = None
        reasoning_output: ReasoningOutput | None = None
        critique_output: CritiqueOutput | None = None
        action_output: ActionOutput | None = None

        for step in plan.steps:
            agent = step.agent

            if agent == "retrieval_agent":
                top_k_raw = step.inputs.get("top_k", 5)
                top_k = top_k_raw if isinstance(top_k_raw, int) else 5
                strategy_raw = step.inputs.get("strategy", "vector")
                strategy = strategy_raw if isinstance(strategy_raw, str) else "vector"
                if strategy not in ("vector", "keyword", "hybrid"):
                    strategy = "vector"
                r_input = RetrievalInput(
                    query=input.user_message,
                    user_id=input.user_id,
                    top_k=top_k,
                    strategy=strategy,  # type: ignore[arg-type]
                )
                retrieval_output = self._retrieval_agent.run(r_input)
                agent_trace.append(
                    {
                        "agent": "retrieval_agent",
                        "chunks_retrieved": len(retrieval_output.chunks),
                    }
                )

            elif agent == "reasoning_agent":
                chunks = retrieval_output.chunks if retrieval_output is not None else []
                rn_input = ReasoningInput(
                    question=input.user_message,
                    chunks=chunks,
                    session_id=input.session_id,
                )
                reasoning_output = self._reasoning_agent.run(rn_input)
                agent_trace.append(
                    {
                        "agent": "reasoning_agent",
                        "confidence": reasoning_output.confidence,
                        "context_adequacy": reasoning_output.context_adequacy,
                    }
                )

            elif agent == "critique_agent":
                if reasoning_output is None:
                    logger.warning(
                        "Skipping critique_agent: no reasoning output available",
                        extra={"session_id": input.session_id},
                    )
                    agent_trace.append({"agent": "critique_agent", "skipped": True})
                    continue
                chunks = retrieval_output.chunks if retrieval_output is not None else []
                c_input = CritiqueInput(
                    question=input.user_message,
                    draft_answer=reasoning_output.answer,
                    chunks=chunks,
                    session_id=input.session_id,
                )
                critique_output = self._critique_agent.run(c_input)
                agent_trace.append(
                    {
                        "agent": "critique_agent",
                        "verdict": critique_output.verdict,
                        "confidence": critique_output.confidence,
                    }
                )

            elif agent == "memory_agent":
                summary_lines = [
                    f"{m['role']}: {m['content']}" for m in input.history[-10:]
                ]
                m_input = MemoryInput(
                    session_id=input.session_id,
                    conversation_summary="\n".join(summary_lines),
                )
                memory_out = self._memory_agent.run(m_input)
                agent_trace.append(
                    {
                        "agent": "memory_agent",
                        "facts_extracted": len(memory_out.facts),
                    }
                )

            elif agent == "action_agent":
                tool_id_raw = step.inputs.get("tool_id", "")
                tool_id = tool_id_raw if isinstance(tool_id_raw, str) else str(tool_id_raw)
                tool_params: dict[str, object] = {
                    k: v for k, v in step.inputs.items() if k != "tool_id"
                }
                a_input = ActionInput(
                    instruction=input.user_message,
                    tool_id=tool_id,
                    tool_params=tool_params,
                    user_id=input.user_id,
                    session_id=input.session_id,
                )
                action_output = self._action_agent.run(a_input)
                agent_trace.append(
                    {
                        "agent": "action_agent",
                        "tool_id": action_output.tool_id,
                        "succeeded": action_output.succeeded,
                    }
                )

        answer = self._synthesize(input, action_output, reasoning_output, critique_output)
        confidence = reasoning_output.confidence if reasoning_output is not None else 0.9

        return OrchestratorOutput(
            answer=answer,
            session_id=input.session_id,
            agent_trace=agent_trace,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _plan(self, input: OrchestratorInput) -> OrchestratorPlan:
        tools = self._action_agent.list_tools()
        history_lines = [
            f"{m['role']}: {m['content'][:200]}" for m in input.history[-10:]
        ]
        retrieval_note = "retrieval available" if input.use_retrieval else "no retrieval"

        prompt = (
            f"USER MESSAGE: {input.user_message}\n\n"
            f"SESSION HISTORY (last {len(history_lines)} turns):\n"
            + ("\n".join(history_lines) if history_lines else "(no history)")
            + f"\n\nAVAILABLE TOOLS: {', '.join(tools) if tools else 'none'}\n"
            f"RETRIEVAL: {retrieval_note}\n\n"
            "Produce an execution plan as JSON:\n"
            '{"steps": [{"agent": "...", "rationale": "...", "inputs": {}}], '
            '"final_synthesis_note": "..."}'
        )

        try:
            ai_response = self._llm.generate(
                AgentInput(user_message=prompt, session_id=input.session_id, history=[])
            )
            raw = self._strip_code_block(ai_response.content)
            data = json.loads(raw)
            steps = [
                AgentStep(
                    agent=s["agent"],
                    rationale=str(s.get("rationale", "")),
                    inputs=s.get("inputs") or {},
                )
                for s in data.get("steps", [])
            ]
            return OrchestratorPlan(
                steps=steps,
                final_synthesis_note=str(data.get("final_synthesis_note", "")),
            )
        except Exception as exc:
            logger.warning(
                "OrchestratorService: planning failed; using fallback plan",
                extra={"error": str(exc), "session_id": input.session_id},
            )
            return OrchestratorPlan(
                steps=[
                    AgentStep(
                        agent="reasoning_agent",
                        rationale="fallback plan",
                        inputs={},
                    )
                ],
                final_synthesis_note="",
            )

    def _synthesize(
        self,
        input: OrchestratorInput,
        action_output: ActionOutput | None,
        reasoning_output: ReasoningOutput | None,
        critique_output: CritiqueOutput | None,
    ) -> str:
        if action_output is not None and action_output.succeeded:
            prompt = (
                f"Original question: {input.user_message}\n"
                f"Tool '{action_output.tool_id}' returned: {action_output.result}\n\n"
                "Provide a natural, conversational answer using this tool result."
            )
            return self._call_synthesis_llm(prompt, input.session_id)

        if reasoning_output is not None:
            if critique_output is not None and critique_output.verdict == "needs_revision":
                prompt = (
                    f"Original question: {input.user_message}\n"
                    f"Draft answer: {reasoning_output.answer}\n"
                    f"Revision instructions: {critique_output.revision_instructions}\n\n"
                    "Provide a revised, accurate answer incorporating the revision instructions."
                )
            else:
                prompt = (
                    f"Original question: {input.user_message}\n"
                    f"Answer: {reasoning_output.answer}\n\n"
                    "Restate this answer in a natural, conversational way."
                )
            return self._call_synthesis_llm(prompt, input.session_id)

        # Pure conversational fallback
        prompt = f"Answer this conversationally: {input.user_message}"
        return self._call_synthesis_llm(prompt, input.session_id)

    def _call_synthesis_llm(self, prompt: str, session_id: str) -> str:
        try:
            ai_response = self._llm.generate(
                AgentInput(user_message=prompt, session_id=session_id, history=[])
            )
            return ai_response.content.strip() or prompt
        except Exception as exc:
            logger.warning(
                "OrchestratorService: synthesis LLM call failed",
                extra={"error": str(exc), "session_id": session_id},
            )
            return prompt

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
