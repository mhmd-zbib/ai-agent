"""
agents.orchestrator.agent — OrchestratorAgent, ExecutionCoordinator, SynthesisService,
and the intra-module Protocol interfaces for all sub-agents.

Merged from:
  packages/api/src/api/modules/agent/protocols.py
  packages/api/src/api/modules/agent/services/orchestrator_service.py
  packages/api/src/api/modules/agent/services/execution_coordinator.py
  packages/api/src/api/modules/agent/services/synthesis_service.py

Import path changes:
  api.modules.agent.protocols         -> (defined locally as Protocol classes)
  api.modules.agent.schemas.sub_agents -> agents.orchestrator.schemas
  api.modules.agent.services.*         -> agents.orchestrator.agent (merged here)
  (shared.* imports are unchanged)
"""

from __future__ import annotations

from typing import Protocol

from agents.core.base import BaseAgent
from agents.core.context import AgentContext, AgentResult
from agents.orchestrator.planner import PlanningService
from agents.orchestrator.schemas import (
    ActionInput,
    ActionOutput,
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
    RetrievalOutput,
)
from shared.config import AgentConfig
from shared.llm.base import BaseLLM
from shared.logging import get_logger
from shared.schemas import AgentInput

__all__ = [
    "ExecutionCoordinator",
    "ExecutionResult",
    "IActionAgent",
    "ICritiqueAgent",
    "IFormulaVerificationAgent",
    "IMemoryAgent",
    "IReasoningAgent",
    "IRetrievalAgent",
    "OrchestratorAgent",
    "SynthesisService",
]

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Intra-module Protocols
# ---------------------------------------------------------------------------


class IRetrievalAgent(Protocol):
    def run(self, input: RetrievalInput) -> RetrievalOutput: ...


class IReasoningAgent(Protocol):
    def run(self, input: ReasoningInput) -> ReasoningOutput: ...


class ICritiqueAgent(Protocol):
    def run(self, input: CritiqueInput) -> CritiqueOutput: ...


class IMemoryAgent(Protocol):
    def run(self, input: MemoryInput) -> MemoryOutput: ...  # type: ignore[name-defined]


class IFormulaVerificationAgent(Protocol):
    def run(self, input: FormulaVerificationInput) -> FormulaVerificationOutput: ...


class IActionAgent(Protocol):
    def run(self, input: ActionInput) -> ActionOutput: ...

    def list_tools(self) -> list[str]: ...


# Re-import MemoryOutput so IMemoryAgent annotation resolves
from agents.orchestrator.schemas import MemoryOutput  # noqa: E402


# ---------------------------------------------------------------------------
# ExecutionResult
# ---------------------------------------------------------------------------


class ExecutionResult:
    """Container for agent execution results."""

    def __init__(self) -> None:
        self.agent_trace: list[dict[str, object]] = []
        self.retrieval_output: RetrievalOutput | None = None
        self.reasoning_output: ReasoningOutput | None = None
        self.critique_output: CritiqueOutput | None = None
        self.action_output: ActionOutput | None = None
        self.formula_verification_output: FormulaVerificationOutput | None = None


# ---------------------------------------------------------------------------
# ExecutionCoordinator
# ---------------------------------------------------------------------------


class ExecutionCoordinator:
    """Coordinate execution of planned agent steps."""

    def __init__(
        self,
        *,
        retrieval_agent: IRetrievalAgent,
        reasoning_agent: IReasoningAgent,
        critique_agent: ICritiqueAgent,
        memory_agent: IMemoryAgent,
        action_agent: IActionAgent,
        formula_verification_agent: IFormulaVerificationAgent,
        config: AgentConfig,
    ) -> None:
        self._retrieval_agent = retrieval_agent
        self._reasoning_agent = reasoning_agent
        self._critique_agent = critique_agent
        self._memory_agent = memory_agent
        self._action_agent = action_agent
        self._formula_verification_agent = formula_verification_agent
        self._config = config

    def execute(
        self, plan: OrchestratorPlan, input: OrchestratorInput
    ) -> ExecutionResult:
        """
        Execute all steps in the plan.

        Args:
            plan: The execution plan with steps to run
            input: Original orchestrator input

        Returns:
            ExecutionResult containing all agent outputs and trace
        """
        result = ExecutionResult()

        for step in plan.steps:
            self._execute_step(step, input, result)

        return result

    def _execute_step(
        self,
        step: "AgentStep",  # noqa: F821 — imported below
        input: OrchestratorInput,
        result: ExecutionResult,
    ) -> None:
        """Execute a single agent step."""
        from agents.orchestrator.schemas import AgentStep as _AgentStep  # local import

        agent = step.agent

        if agent == "retrieval_agent":
            self._execute_retrieval(step, input, result)
        elif agent == "reasoning_agent":
            self._execute_reasoning(input, result)
        elif agent == "critique_agent":
            self._execute_critique(input, result)
        elif agent == "memory_agent":
            self._execute_memory(input, result)
        elif agent == "formula_verification_agent":
            self._execute_formula_verification(step, input, result)
        elif agent == "action_agent":
            self._execute_action(step, input, result)

    def _execute_retrieval(
        self,
        step: object,
        input: OrchestratorInput,
        result: ExecutionResult,
    ) -> None:
        """Execute retrieval agent step."""
        from agents.orchestrator.schemas import AgentStep

        assert isinstance(step, AgentStep)
        top_k_raw = step.inputs.get("top_k", self._config.default_retrieval_top_k)
        top_k = (
            top_k_raw
            if isinstance(top_k_raw, int)
            else self._config.default_retrieval_top_k
        )

        strategy_raw = step.inputs.get("strategy", "vector")
        strategy = strategy_raw if isinstance(strategy_raw, str) else "vector"
        if strategy not in ("vector", "keyword", "hybrid"):
            strategy = "vector"

        retrieval_query = self._expand_query(input.user_message, input.history)

        r_input = RetrievalInput(
            query=retrieval_query,
            user_id=input.user_id,
            top_k=top_k,
            strategy=strategy,  # type: ignore[arg-type]
            course_code=input.course_code,
            university_name=input.university_name,
        )

        result.retrieval_output = self._retrieval_agent.run(r_input)
        result.agent_trace.append(
            {
                "agent": "retrieval_agent",
                "chunks_retrieved": len(result.retrieval_output.chunks),
                "query_used": retrieval_query,
            }
        )

    def _execute_reasoning(
        self, input: OrchestratorInput, result: ExecutionResult
    ) -> None:
        """Execute reasoning agent step."""
        chunks = (
            result.retrieval_output.chunks if result.retrieval_output is not None else []
        )

        rn_input = ReasoningInput(
            question=input.user_message,
            chunks=chunks,
            session_id=input.session_id,
            history=input.history,
        )

        result.reasoning_output = self._reasoning_agent.run(rn_input)
        result.agent_trace.append(
            {
                "agent": "reasoning_agent",
                "confidence": result.reasoning_output.confidence,
                "context_adequacy": result.reasoning_output.context_adequacy,
            }
        )

    def _execute_critique(
        self, input: OrchestratorInput, result: ExecutionResult
    ) -> None:
        """Execute critique agent step."""
        if result.reasoning_output is None:
            logger.warning(
                "Skipping critique_agent: no reasoning output available",
                extra={"session_id": input.session_id},
            )
            result.agent_trace.append({"agent": "critique_agent", "skipped": True})
            return

        chunks = (
            result.retrieval_output.chunks if result.retrieval_output is not None else []
        )

        c_input = CritiqueInput(
            question=input.user_message,
            draft_answer=result.reasoning_output.answer,
            chunks=chunks,
            session_id=input.session_id,
        )

        result.critique_output = self._critique_agent.run(c_input)
        result.agent_trace.append(
            {
                "agent": "critique_agent",
                "verdict": result.critique_output.verdict,
                "confidence": result.critique_output.confidence,
            }
        )

    def _execute_memory(
        self, input: OrchestratorInput, result: ExecutionResult
    ) -> None:
        """Execute memory agent step."""
        summary_lines = [
            f"{m['role']}: {m['content']}"
            for m in input.history[-self._config.orchestrator_history_window :]
        ]

        m_input = MemoryInput(
            session_id=input.session_id,
            conversation_summary="\n".join(summary_lines),
        )

        memory_out = self._memory_agent.run(m_input)
        result.agent_trace.append(
            {
                "agent": "memory_agent",
                "facts_extracted": len(memory_out.facts),
            }
        )

    def _execute_formula_verification(
        self,
        step: object,
        input: OrchestratorInput,
        result: ExecutionResult,
    ) -> None:
        """Execute formula verification agent step."""
        from agents.orchestrator.schemas import AgentStep

        assert isinstance(step, AgentStep)
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

        chunks = (
            result.retrieval_output.chunks if result.retrieval_output is not None else []
        )

        fv_input = FormulaVerificationInput(
            session_id=input.session_id,
            problem=problem,
            formula=formula,
            variables=fv_variables,
            context_chunks=chunks,
        )

        result.formula_verification_output = self._formula_verification_agent.run(
            fv_input
        )
        result.agent_trace.append(
            {
                "agent": "formula_verification_agent",
                "verdict": result.formula_verification_output.verdict,
                "confidence": result.formula_verification_output.confidence,
                "explanation": result.formula_verification_output.explanation,
            }
        )

    def _execute_action(
        self,
        step: object,
        input: OrchestratorInput,
        result: ExecutionResult,
    ) -> None:
        """Execute action agent step."""
        from agents.orchestrator.schemas import AgentStep

        assert isinstance(step, AgentStep)
        tool_id_raw = step.inputs.get("tool_id") or step.inputs.get("tool", "")
        tool_id = tool_id_raw if isinstance(tool_id_raw, str) else str(tool_id_raw)

        tool_params: dict[str, object] = {
            k: v for k, v in step.inputs.items() if k != "tool_id"
        }

        if (
            result.formula_verification_output is not None
            and result.formula_verification_output.verdict == "needs_revision"
            and result.formula_verification_output.corrected_formula is not None
            and tool_id == "scientific_calc"
        ):
            tool_params["formula"] = (
                result.formula_verification_output.corrected_formula
            )
            logger.info(
                "Applied corrected formula from formula_verification_agent",
                extra={"session_id": input.session_id},
            )

        a_input = ActionInput(
            instruction=input.user_message,
            tool_id=tool_id,
            tool_params=tool_params,
            user_id=input.user_id,
            session_id=input.session_id,
        )

        result.action_output = self._action_agent.run(a_input)
        result.agent_trace.append(
            {
                "agent": "action_agent",
                "tool_id": result.action_output.tool_id,
                "succeeded": result.action_output.succeeded,
            }
        )

    def _expand_query(self, user_message: str, history: list[dict[str, str]]) -> str:
        """
        Make a follow-up question self-contained for embedding.

        Combines the last user+assistant exchange with the current message so
        pronouns like "he", "it", "they" can be resolved by the embedding model.
        No extra LLM call — just lightweight string concatenation.
        """
        if not history:
            return user_message

        recent = history[-2:]
        context_parts = [m.get("content", "")[:200] for m in recent]
        combined = "  ".join(p for p in context_parts if p)
        return f"{combined}  {user_message}"


# ---------------------------------------------------------------------------
# SynthesisService
# ---------------------------------------------------------------------------


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
        """
        if (
            reasoning_output is not None
            and reasoning_output.context_adequacy == "sufficient"
        ):
            return self._synthesize_reasoning_output(
                input, reasoning_output, critique_output
            )

        if action_output is not None and action_output.succeeded:
            return self._synthesize_action_output(input, action_output)

        if reasoning_output is not None and input.use_retrieval:
            return self._no_information_message(input.user_message)

        if reasoning_output is not None:
            return self._synthesize_conversational(input, reasoning_output)

        if input.use_retrieval:
            return self._no_information_message(input.user_message)

        return "I'm sorry, I was unable to process your request. Please try again."

    def _synthesize_reasoning_output(
        self,
        input: OrchestratorInput,
        reasoning_output: ReasoningOutput,
        critique_output: CritiqueOutput | None,
    ) -> str:
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
        prompt = (
            f"Original question: {input.user_message}\n"
            f"Answer: {reasoning_output.answer}\n\n"
            "Restate this answer in a natural, conversational way. "
            "Do NOT add any information beyond what is in the Answer above."
        )
        return self._call_synthesis_llm(prompt, input.session_id)

    def _no_information_message(self, user_message: str) -> str:
        return (
            "I could not find relevant information in your uploaded documents "
            f'to answer: "{user_message}". '
            "Please make sure the relevant document has been uploaded and processed."
        )

    def _call_synthesis_llm(self, prompt: str, session_id: str) -> str:
        try:
            ai_response = self._synthesis_llm.generate(
                AgentInput(user_message=prompt, session_id=session_id, history=[])
            )
            return ai_response.content.strip() or prompt
        except Exception as exc:
            logger.warning(
                "Synthesis LLM call failed",
                extra={"error": str(exc), "session_id": session_id},
            )
            return prompt


# ---------------------------------------------------------------------------
# OrchestratorAgent — implements BaseAgent
# ---------------------------------------------------------------------------


class OrchestratorAgent(BaseAgent):
    """
    Multi-agent orchestrator that implements BaseAgent.

    Delegates to PlanningService, ExecutionCoordinator, and SynthesisService.
    """

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
        config: AgentConfig,
    ) -> None:
        self._planning_service = PlanningService(
            llm=llm,
            action_agent=action_agent,
            config=config,
        )

        self._execution_coordinator = ExecutionCoordinator(
            retrieval_agent=retrieval_agent,
            reasoning_agent=reasoning_agent,
            critique_agent=critique_agent,
            memory_agent=memory_agent,
            action_agent=action_agent,
            formula_verification_agent=formula_verification_agent,
            config=config,
        )

        self._synthesis_service = SynthesisService(synthesis_llm=synthesis_llm)
        self._config = config

    async def run(self, context: AgentContext) -> AgentResult:
        """
        Execute the multi-agent pipeline given an AgentContext.

        Converts AgentContext to OrchestratorInput, runs the pipeline, then
        wraps OrchestratorOutput back into AgentResult.
        """
        use_retrieval = bool(context.metadata.get("use_retrieval", False))
        course_code = str(context.metadata.get("course_code", ""))
        university_name = str(context.metadata.get("university_name", ""))

        orch_input = OrchestratorInput(
            user_message=context.user_message,
            session_id=context.session_id,
            history=context.history,
            user_id=context.user_id,
            use_retrieval=use_retrieval,
            course_code=course_code,
            university_name=university_name,
        )

        orch_output = self._run_sync(orch_input)

        return AgentResult(
            content=orch_output.answer,
            response_type="text",
            metadata={
                "confidence": orch_output.confidence,
                "agent_trace": orch_output.agent_trace,
            },
        )

    def _run_sync(self, input: OrchestratorInput) -> OrchestratorOutput:
        """Synchronous orchestration pipeline."""
        plan = self._planning_service.create_plan(input)
        execution_result = self._execution_coordinator.execute(plan, input)

        answer = self._synthesis_service.synthesize(
            input=input,
            action_output=execution_result.action_output,
            reasoning_output=execution_result.reasoning_output,
            critique_output=execution_result.critique_output,
        )

        confidence = (
            execution_result.reasoning_output.confidence
            if execution_result.reasoning_output is not None
            else self._config.default_confidence
        )

        return OrchestratorOutput(
            answer=answer,
            session_id=input.session_id,
            agent_trace=execution_result.agent_trace,
            confidence=confidence,
        )
