"""
OrchestratorService — thin facade coordinating planning, execution, and synthesis.

This service delegates to three focused services following Single Responsibility Principle:
- PlanningService: Generate execution plans
- ExecutionCoordinator: Execute agent steps
- SynthesisService: Combine outputs into final answer
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
    OrchestratorInput,
    OrchestratorOutput,
)
from app.modules.agent.services.execution_coordinator import ExecutionCoordinator
from app.modules.agent.services.planning_service import PlanningService
from app.modules.agent.services.synthesis_service import SynthesisService
from app.shared.config import AgentConfig
from app.shared.llm.base import BaseLLM
from app.shared.logging import get_logger

logger = get_logger(__name__)



class OrchestratorService:
    """
    Orchestrator facade that delegates to specialized services.
    
    This thin coordinator follows the facade pattern, delegating to:
    - PlanningService for plan generation
    - ExecutionCoordinator for agent execution
    - SynthesisService for answer synthesis
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
        # Initialize specialized services
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

    def run(self, input: OrchestratorInput) -> OrchestratorOutput:
        """
        Orchestrate multi-agent execution.
        
        Steps:
        1. Generate execution plan (PlanningService)
        2. Execute planned steps (ExecutionCoordinator)
        3. Synthesize final answer (SynthesisService)
        
        Args:
            input: Orchestrator input with user message, history, and context
            
        Returns:
            Orchestrator output with answer, trace, and confidence
        """
        # Step 1: Planning
        plan = self._planning_service.create_plan(input)
        
        # Step 2: Execution
        execution_result = self._execution_coordinator.execute(plan, input)
        
        # Step 3: Synthesis
        answer = self._synthesis_service.synthesize(
            input=input,
            action_output=execution_result.action_output,
            reasoning_output=execution_result.reasoning_output,
            critique_output=execution_result.critique_output,
        )
        
        # Calculate confidence from reasoning output or use default
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

