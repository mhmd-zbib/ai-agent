"""
RetrievalAgent — orchestrates retrieval strategies (vector/keyword/hybrid).

Delegates actual vector search to RAGService; keyword search is a stub
pending BM25 integration.
"""
from __future__ import annotations

from app.modules.agent.schemas.sub_agents import (
    RetrievalInput,
    RetrievalOutput,
    RetrievedChunk,
)
from app.modules.rag.schemas import SearchQuery
from app.modules.rag.services.rag_service import RAGService
from app.shared.logging import get_logger

logger = get_logger(__name__)


class RetrievalAgent:
    def __init__(self, *, rag_service: RAGService | None) -> None:
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
            results = self._rag_service.search(
                SearchQuery(text=input.query, top_k=input.top_k, user_id=input.user_id)
            )
            return [
                RetrievedChunk(
                    chunk_id=r.chunk_id,
                    score=r.score,
                    text=r.text,
                    source=r.source,
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
        # Stub: no BM25 yet — graceful degradation
        logger.debug("Keyword search stub: returning empty results", extra={"query": input.query})
        return []
