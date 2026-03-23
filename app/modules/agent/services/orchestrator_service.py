"""
OrchestratorService — plans and delegates to focused sub-agents.
"""

from __future__ import annotations

import json

from app.modules.agent.protocols import (
    IActionAgent,
    ICritiqueAgent,
    IFormulaVerificationAgent,
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
    FormulaVerificationInput,
    FormulaVerificationOutput,
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
        synthesis_llm: BaseLLM,
        retrieval_agent: IRetrievalAgent,
        reasoning_agent: IReasoningAgent,
        critique_agent: ICritiqueAgent,
        memory_agent: IMemoryAgent,
        action_agent: IActionAgent,
        formula_verification_agent: IFormulaVerificationAgent,
    ) -> None:
        self._llm = llm
        self._synthesis_llm = synthesis_llm
        self._retrieval_agent = retrieval_agent
        self._reasoning_agent = reasoning_agent
        self._critique_agent = critique_agent
        self._memory_agent = memory_agent
        self._action_agent = action_agent
        self._formula_verification_agent = formula_verification_agent

    def run(self, input: OrchestratorInput) -> OrchestratorOutput:
        plan = self._plan(input)

        agent_trace: list[dict[str, object]] = []
        retrieval_output = None
        reasoning_output: ReasoningOutput | None = None
        critique_output: CritiqueOutput | None = None
        action_output: ActionOutput | None = None
        formula_verification_output: FormulaVerificationOutput | None = None

        for step in plan.steps:
            agent = step.agent

            if agent == "retrieval_agent":
                top_k_raw = step.inputs.get("top_k", 5)
                top_k = top_k_raw if isinstance(top_k_raw, int) else 5
                strategy_raw = step.inputs.get("strategy", "vector")
                strategy = strategy_raw if isinstance(strategy_raw, str) else "vector"
                if strategy not in ("vector", "keyword", "hybrid"):
                    strategy = "vector"
                # Expand the query using history so pronouns / references resolve
                # correctly at the embedding level (e.g. "where was he?" → self-contained).
                retrieval_query = self._expand_query(input.user_message, input.history)
                r_input = RetrievalInput(
                    query=retrieval_query,
                    user_id=input.user_id,
                    top_k=top_k,
                    strategy=strategy,  # type: ignore[arg-type]
                    course_code=input.course_code,
                    university_name=input.university_name,
                )
                retrieval_output = self._retrieval_agent.run(r_input)
                agent_trace.append(
                    {
                        "agent": "retrieval_agent",
                        "chunks_retrieved": len(retrieval_output.chunks),
                        "query_used": retrieval_query,
                    }
                )

            elif agent == "reasoning_agent":
                chunks = retrieval_output.chunks if retrieval_output is not None else []
                rn_input = ReasoningInput(
                    question=input.user_message,
                    chunks=chunks,
                    session_id=input.session_id,
                    history=input.history,
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

            elif agent == "formula_verification_agent":
                formula_raw = step.inputs.get("formula", "")
                formula = formula_raw if isinstance(formula_raw, str) else str(formula_raw)
                variables_raw = step.inputs.get("variables", {})
                fv_variables: dict[str, float] = {}
                if isinstance(variables_raw, dict):
                    for k, v in variables_raw.items():
                        try:
                            fv_variables[str(k)] = float(v)  # type: ignore[arg-type]
                        except (TypeError, ValueError):
                            pass
                problem_raw = step.inputs.get("problem", input.user_message)
                problem = problem_raw if isinstance(problem_raw, str) else input.user_message
                chunks = retrieval_output.chunks if retrieval_output is not None else []
                fv_input = FormulaVerificationInput(
                    session_id=input.session_id,
                    problem=problem,
                    formula=formula,
                    variables=fv_variables,
                    context_chunks=chunks,
                )
                formula_verification_output = self._formula_verification_agent.run(fv_input)
                agent_trace.append(
                    {
                        "agent": "formula_verification_agent",
                        "verdict": formula_verification_output.verdict,
                        "confidence": formula_verification_output.confidence,
                        "explanation": formula_verification_output.explanation,
                    }
                )

            elif agent == "action_agent":
                # Accept "tool_id" or "tool" — LLMs sometimes use the latter
                tool_id_raw = step.inputs.get("tool_id") or step.inputs.get("tool", "")
                tool_id = (
                    tool_id_raw if isinstance(tool_id_raw, str) else str(tool_id_raw)
                )
                tool_params: dict[str, object] = {
                    k: v for k, v in step.inputs.items() if k != "tool_id"
                }
                # If formula verification found an error and produced a correction,
                # substitute the corrected formula transparently for scientific_calc.
                if (
                    formula_verification_output is not None
                    and formula_verification_output.verdict == "needs_revision"
                    and formula_verification_output.corrected_formula is not None
                    and tool_id == "scientific_calc"
                ):
                    tool_params["formula"] = formula_verification_output.corrected_formula
                    logger.info(
                        "OrchestratorService: applied corrected formula from formula_verification_agent",
                        extra={"session_id": input.session_id},
                    )
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

        answer = self._synthesize(
            input, action_output, reasoning_output, critique_output
        )
        confidence = (
            reasoning_output.confidence if reasoning_output is not None else 0.9
        )

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
        retrieval_note = (
            "RETRIEVAL ENABLED — user has uploaded course documents. "
            "Use retrieval_agent + reasoning_agent for any question that may be answered "
            "from those documents. Only use action_agent tools (calculator, weather, etc.) "
            "for data that cannot come from documents (real-time data, computations)."
            if input.use_retrieval
            else "no retrieval"
        )

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
                AgentInput(user_message=prompt, session_id=input.session_id, history=[]),
                response_mode="json",
            )
            raw = self._strip_code_block(ai_response.content)
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

            # Safety net: when use_retrieval=True the RAG core
            # (retrieval_agent → reasoning_agent) must always run.
            # The planning LLM frequently drops one or both steps as history
            # grows — enforce them deterministically so retrieved context is
            # always passed to the reasoning agent.
            if input.use_retrieval:
                if not any(s.agent == "retrieval_agent" for s in steps):
                    steps.insert(
                        0,
                        AgentStep(
                            agent="retrieval_agent",
                            rationale="Forced: retrieve relevant document chunks",
                            inputs={"top_k": 5, "strategy": "vector"},
                        ),
                    )
                if not any(s.agent == "reasoning_agent" for s in steps):
                    # Insert reasoning_agent right after retrieval_agent
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

            return OrchestratorPlan(
                steps=steps,
                final_synthesis_note=str(data.get("final_synthesis_note", "")),
            )
        except Exception as exc:
            logger.warning(
                "OrchestratorService: planning failed; using fallback plan",
                extra={"error": str(exc), "session_id": input.session_id},
            )
            fallback_steps: list[AgentStep] = []
            if input.use_retrieval:
                fallback_steps.append(
                    AgentStep(
                        agent="retrieval_agent",
                        rationale="fallback plan",
                        inputs={"top_k": 5, "strategy": "vector"},
                    )
                )
            fallback_steps.append(
                AgentStep(agent="reasoning_agent", rationale="fallback plan", inputs={})
            )
            return OrchestratorPlan(steps=fallback_steps, final_synthesis_note="")

    def _synthesize(
        self,
        input: OrchestratorInput,
        action_output: ActionOutput | None,
        reasoning_output: ReasoningOutput | None,
        critique_output: CritiqueOutput | None,
    ) -> str:
        # Document-grounded answers take priority when the reasoning agent found
        # sufficient context.  Action-agent tool results (web_search, weather…)
        # are only used when documents could NOT answer the question.
        if (
            reasoning_output is not None
            and reasoning_output.context_adequacy == "sufficient"
        ):
            if (
                critique_output is not None
                and critique_output.verdict == "needs_revision"
            ):
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

        # Tool result available (action_agent ran successfully).
        if action_output is not None and action_output.succeeded:
            prompt = (
                f"Original question: {input.user_message}\n"
                f"Tool '{action_output.tool_id}' returned: {action_output.result}\n\n"
                "Provide a natural, conversational answer using this tool result. "
                "Do NOT add any information beyond what the tool returned."
            )
            return self._call_synthesis_llm(prompt, input.session_id)

        # Reasoning ran but context was insufficient — do NOT hallucinate.
        # Return a clear "no information" message so the user knows to upload docs.
        if reasoning_output is not None and input.use_retrieval:
            return (
                "I could not find relevant information in your uploaded documents "
                f"to answer: \"{input.user_message}\". "
                "Please make sure the relevant document has been uploaded and processed."
            )

        # Reasoning ran without retrieval (conversational mode) — rephrase safely.
        if reasoning_output is not None:
            prompt = (
                f"Original question: {input.user_message}\n"
                f"Answer: {reasoning_output.answer}\n\n"
                "Restate this answer in a natural, conversational way. "
                "Do NOT add any information beyond what is in the Answer above."
            )
            return self._call_synthesis_llm(prompt, input.session_id)

        # No reasoning or tool output at all.
        if input.use_retrieval:
            return (
                "I could not find relevant information in your uploaded documents "
                f"to answer: \"{input.user_message}\". "
                "Please make sure the relevant document has been uploaded and processed."
            )

        return "I'm sorry, I was unable to process your request. Please try again."

    def _call_synthesis_llm(self, prompt: str, session_id: str) -> str:
        try:
            ai_response = self._synthesis_llm.generate(
                AgentInput(user_message=prompt, session_id=session_id, history=[])
            )
            return ai_response.content.strip() or prompt
        except Exception as exc:
            logger.warning(
                "OrchestratorService: synthesis LLM call failed",
                extra={"error": str(exc), "session_id": session_id},
            )
            return prompt

    def _expand_query(self, user_message: str, history: list[dict[str, str]]) -> str:
        """
        Make a follow-up question self-contained for embedding.

        Combines the last user+assistant exchange with the current message so
        pronouns like "he", "it", "they" can be resolved by the embedding model.
        No extra LLM call — just lightweight string concatenation.

        Examples
        --------
        history  : ["user: what was batman doing?", "assistant: eating ice cream"]
        question : "where was he?"
        result   : "what was batman doing? eating ice cream  where was he?"
        """
        if not history:
            return user_message

        # Take the last user + assistant turn (up to 2 messages)
        recent = history[-2:]
        context_parts = [m.get("content", "")[:200] for m in recent]
        combined = "  ".join(p for p in context_parts if p)
        return f"{combined}  {user_message}"

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
