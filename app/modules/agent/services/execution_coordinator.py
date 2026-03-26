"""
ExecutionCoordinator — coordinates execution of planned agent steps.

Responsibility: Execute agent steps in sequence, manage state between agents,
and build the execution trace.
"""

from __future__ import annotations

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
    OrchestratorPlan,
    ReasoningInput,
    ReasoningOutput,
    RetrievalInput,
    RetrievalOutput,
)
from app.shared.config import AgentConfig
from app.shared.logging import get_logger

logger = get_logger(__name__)


class ExecutionResult:
    """Container for agent execution results."""

    def __init__(self) -> None:
        self.agent_trace: list[dict[str, object]] = []
        self.retrieval_output: RetrievalOutput | None = None
        self.reasoning_output: ReasoningOutput | None = None
        self.critique_output: CritiqueOutput | None = None
        self.action_output: ActionOutput | None = None
        self.formula_verification_output: FormulaVerificationOutput | None = None


class ExecutionCoordinator:
    """Coordinate execution of agent steps."""

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
        step: AgentStep,
        input: OrchestratorInput,
        result: ExecutionResult,
    ) -> None:
        """Execute a single agent step."""
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
        step: AgentStep,
        input: OrchestratorInput,
        result: ExecutionResult,
    ) -> None:
        """Execute retrieval agent step."""
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

        # Expand query for better embedding matching
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
        step: AgentStep,
        input: OrchestratorInput,
        result: ExecutionResult,
    ) -> None:
        """Execute formula verification agent step."""
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
        step: AgentStep,
        input: OrchestratorInput,
        result: ExecutionResult,
    ) -> None:
        """Execute action agent step."""
        # Accept "tool_id" or "tool" — LLMs sometimes use the latter
        tool_id_raw = step.inputs.get("tool_id") or step.inputs.get("tool", "")
        tool_id = tool_id_raw if isinstance(tool_id_raw, str) else str(tool_id_raw)

        tool_params: dict[str, object] = {
            k: v for k, v in step.inputs.items() if k != "tool_id"
        }

        # If formula verification found an error and produced a correction,
        # substitute the corrected formula transparently for scientific_calc.
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
                session_id=input.session_id,
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

        # Take the last user + assistant turn (up to 2 messages)
        recent = history[-2:]
        context_parts = [m.get("content", "")[:200] for m in recent]
        combined = "  ".join(p for p in context_parts if p)
        return f"{combined}  {user_message}"
