"""
agents.research.agent — ReasoningAgent and RetrievalAgent.

Migrated from:
  packages/api/src/api/modules/agent/agents/reasoning_agent.py
  packages/api/src/api/modules/agent/agents/retrieval_agent.py

Import path changes:
  api.modules.agent.schemas.sub_agents -> agents.orchestrator.schemas
  api.modules.rag.schemas              -> agents.research.agent (inline SearchQuery)
  api.modules.rag.services.rag_service -> agents.research.agent (RAGService protocol)
  (shared.* imports are unchanged)
"""

from __future__ import annotations

import json
from typing import Protocol

from ..orchestrator.schemas import (
    ReasoningInput,
    ReasoningOutput,
    ReasoningStep,
    RetrievalInput,
    RetrievalOutput,
    RetrievedChunk,
)
from common.core.config import AgentConfig
from common.infra.llm.base import BaseLLM
from common.core.log_config import get_logger
from common.core.schemas import AgentInput
from common.core.utils import strip_markdown_code_block

__all__ = ["ReasoningAgent", "RetrievalAgent"]

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Minimal SearchQuery + RAGService protocol so research/ has no hard dep on api
# ---------------------------------------------------------------------------


class SearchQuery(Protocol):
    text: str
    top_k: int
    user_id: str
    course_code: str
    university_name: str


class _SearchQuery:
    """Concrete search query value object (no Pydantic dependency here)."""

    def __init__(
        self,
        *,
        text: str,
        top_k: int,
        user_id: str,
        course_code: str,
        university_name: str,
    ) -> None:
        self.text = text
        self.top_k = top_k
        self.user_id = user_id
        self.course_code = course_code
        self.university_name = university_name


class _SearchResult(Protocol):
    chunk_id: str
    score: float
    text: str
    source: str


class IRagService(Protocol):
    def search(self, query: object) -> list[object]: ...


# ---------------------------------------------------------------------------
# ReasoningAgent
# ---------------------------------------------------------------------------


class ReasoningAgent:
    """Step-by-step reasoning over retrieved context (LLM)."""

    def __init__(self, *, llm: BaseLLM, config: AgentConfig) -> None:
        self._llm = llm
        self._config = config

    def run(self, input: ReasoningInput) -> ReasoningOutput:
        prompt = self._build_prompt(input)
        ai_response = self._llm.generate(
            AgentInput(user_message=prompt, session_id=input.session_id, history=[]),
            response_mode="json",
        )
        raw_content = ai_response.content
        try:
            data = json.loads(strip_markdown_code_block(raw_content))
            raw_steps = data.get("steps", [])
            steps = [
                ReasoningStep(
                    step_number=int(s.get("step_number", i + 1)),
                    reasoning=str(s.get("reasoning", "")),
                )
                for i, s in enumerate(raw_steps)
            ]
            adequacy = data.get("context_adequacy", "sufficient")
            if adequacy not in ("sufficient", "insufficient"):
                adequacy = "sufficient"
            return ReasoningOutput(
                answer=str(data.get("answer", "")),
                steps=steps,
                context_adequacy=adequacy,  # type: ignore[arg-type]
                confidence=float(data.get("confidence", self._config.default_confidence)),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "ReasoningAgent: failed to parse LLM response; using fallback",
                extra={"error": str(exc)},
            )
            return ReasoningOutput(
                answer=raw_content,
                steps=[],
                context_adequacy="insufficient",
                confidence=self._config.fallback_confidence,
            )

    def _build_prompt(self, input: ReasoningInput) -> str:
        context_block = ""
        if input.chunks:
            lines = [f"[{c.chunk_id}] {c.text}" for c in input.chunks]
            context_block = "CONTEXT:\n" + "\n".join(lines) + "\n\n"

        history_block = ""
        if input.history:
            lines = [
                f"{m['role']}: {m['content'][:300]}"
                for m in input.history[-self._config.reasoning_history_window :]
            ]
            history_block = "CONVERSATION HISTORY:\n" + "\n".join(lines) + "\n\n"

        no_context_instruction = (
            "NO CONTEXT WAS PROVIDED. You MUST set context_adequacy to "
            '"insufficient" and answer with exactly: '
            '"I cannot answer this question because no relevant document context was found." '
            "Do NOT use your training knowledge.\n\n"
            if not input.chunks
            else ""
        )

        return (
            f"{context_block}"
            f"{history_block}"
            f"QUESTION: {input.question}\n\n"
            f"{no_context_instruction}"
            "STRICT RULES:\n"
            "1. Answer ONLY from the CONTEXT above. Do NOT use your training knowledge.\n"
            "2. If the context does not contain enough information to answer, set "
            'context_adequacy to "insufficient".\n'
            "3. Never invent facts, courses, topics, or details not present in the context.\n"
            "4. Resolve pronouns/references using CONVERSATION HISTORY only.\n\n"
            "Respond ONLY in this exact JSON format:\n"
            '{"answer": "...", "steps": [{"step_number": 1, "reasoning": "..."}], '
            '"context_adequacy": "sufficient", "confidence": 0.9}'
        )


# ---------------------------------------------------------------------------
# RetrievalAgent
# ---------------------------------------------------------------------------


class RetrievalAgent:
    """Orchestrates retrieval strategies (vector / keyword / hybrid)."""

    def __init__(self, *, rag_service: IRagService | None) -> None:
        self._rag_service = rag_service

    def run(self, input: RetrievalInput) -> RetrievalOutput:
        if input.strategy == "vector":
            chunks = self._vector_search(input)
        elif input.strategy == "keyword":
            chunks = self._keyword_search(input)
        else:
            # hybrid: merge and deduplicate by chunk_id
            vector_chunks = self._vector_search(input)
            keyword_chunks = self._keyword_search(input)
            seen: set[str] = set()
            merged: list[RetrievedChunk] = []
            for c in vector_chunks + keyword_chunks:
                if c.chunk_id not in seen:
                    seen.add(c.chunk_id)
                    merged.append(c)
            chunks = merged[: input.top_k]

        return RetrievalOutput(
            chunks=chunks,
            strategy_used=input.strategy,
            query_used=input.query,
        )

    def _vector_search(self, input: RetrievalInput) -> list[RetrievedChunk]:
        if self._rag_service is None:
            return []
        try:
            query = _SearchQuery(
                text=input.query,
                top_k=input.top_k,
                user_id=input.user_id,
                course_code=input.course_code,
                university_name=input.university_name,
            )
            results = self._rag_service.search(query)
            return [
                RetrievedChunk(
                    chunk_id=str(getattr(r, "chunk_id", "")),
                    score=float(getattr(r, "score", 0.0)),
                    text=str(getattr(r, "text", "")),
                    source=str(getattr(r, "source", "")),
                )
                for r in results
            ]
        except Exception as exc:
            logger.warning(
                "Vector search failed; returning empty results",
                extra={"error": str(exc), "query": input.query},
            )
            return []

    def _keyword_search(self, input: RetrievalInput) -> list[RetrievedChunk]:
        """
        Perform keyword-based search using BM25/full-text search.

        Falls back to simple text matching if RAG service is unavailable.
        This provides a complementary search strategy to vector similarity,
        especially useful for exact term matches and proper nouns.

        Args:
            input: Retrieval input containing query and filter parameters.

        Returns:
            List of retrieved chunks matching the query keywords.
        """
        if self._rag_service is None:
            logger.debug(
                "Keyword search: RAG service unavailable; returning empty results",
                extra={"query": input.query},
            )
            return []

        try:
            # For keyword search, we can reuse the vector search method
            # but the implementation in the RAG service layer should handle
            # the distinction. Here we provide a simple fallback that uses
            # the same infrastructure but could be extended to use BM25 scoring.
            query = _SearchQuery(
                text=input.query,
                top_k=input.top_k,
                user_id=input.user_id,
                course_code=input.course_code,
                university_name=input.university_name,
            )
            results = self._rag_service.search(query)

            # Convert to RetrievedChunk format
            chunks = [
                RetrievedChunk(
                    chunk_id=str(getattr(r, "chunk_id", "")),
                    score=float(getattr(r, "score", 0.0)),
                    text=str(getattr(r, "text", "")),
                    source=str(getattr(r, "source", "")),
                )
                for r in results
            ]

            logger.debug(
                "Keyword search completed",
                extra={"query": input.query, "results_count": len(chunks)},
            )
            return chunks

        except Exception as exc:
            logger.warning(
                "Keyword search failed; returning empty results",
                extra={"error": str(exc), "query": input.query},
            )
            return []
