"""Search service — RAG retrieval with optional reranking."""

import logging
from abc import ABC, abstractmethod
from collections import defaultdict

from api.search.schemas import SearchQuery, SearchResult
from shared.config import RagConfig
from shared.protocols import IEmbeddingClient, IVectorClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reranker hierarchy
# ---------------------------------------------------------------------------


class BaseReranker(ABC):
    """Abstract base class for reranking strategies (Strategy Pattern)."""

    @abstractmethod
    def rerank(self, items: list[SearchResult]) -> list[SearchResult]: ...


class PassthroughReranker(BaseReranker):
    """Passes items through without modification (testing/fallback)."""

    def rerank(self, items: list[SearchResult]) -> list[SearchResult]:
        return items


class ScoreBasedReranker(BaseReranker):
    """Sorts items by score in descending order."""

    def rerank(self, items: list[SearchResult]) -> list[SearchResult]:
        return sorted(items, key=lambda x: x.score, reverse=True)


class Reranker(BaseReranker):
    """Stub reranker — replace with cross-encoder model."""

    def rerank(self, items: list[SearchResult]) -> list[SearchResult]:
        raise NotImplementedError(
            "Reranker is a stub. Use PassthroughReranker for now."
        )


# ---------------------------------------------------------------------------
# RAG service
# ---------------------------------------------------------------------------


class RAGService:
    """
    Retrieval-Augmented Generation service.

    Pipeline:
    1. Embed the query
    2. Vector similarity search (over-fetch for diversity)
    3. Interleave results across documents (diversity)
    4. Optional reranking
    """

    def __init__(
        self,
        vector_client: IVectorClient | None,
        embedding_client: IEmbeddingClient | None,
        reranker: BaseReranker,
        rag_config: RagConfig,
        enable_reranking: bool = True,
    ) -> None:
        self._vector_client = vector_client
        self._embedding_client = embedding_client
        self._reranker = reranker
        self._rag_config = rag_config
        self._enable_reranking = enable_reranking

    def search(self, query: SearchQuery) -> list[SearchResult]:
        if self._vector_client is None or self._embedding_client is None:
            logger.warning("RAGService: vector or embedding client not configured; returning []")
            return []

        logger.info("RAGService: searching", extra={"query": query.text, "top_k": query.top_k})

        try:
            payload_filter: dict[str, str] = {}
            if query.course_code:
                payload_filter["course_code"] = query.course_code
            if query.university_name:
                payload_filter["university_name"] = query.university_name

            vector = self._embedding_client.embed(query.text)
            fetch_k = query.top_k * self._rag_config.fetch_multiplier
            raw_hits = self._vector_client.query(
                vector=vector,
                top_k=fetch_k,
                namespace=query.user_id,
                filter=payload_filter if payload_filter else None,
            )
        except Exception as exc:
            logger.error("RAGService: vector search failed", extra={"error": str(exc)})
            raise RuntimeError(f"Search failed for query: {query.text}") from exc

        hits = [
            SearchResult(
                chunk_id=str(r.get("id", "")),
                score=float(r.get("score", 0.0)),
                text=str((r.get("metadata") or {}).get("chunk_text", "")),
                source=str((r.get("metadata") or {}).get("file_name", "")),
                document_id=str((r.get("metadata") or {}).get("document_id", "")),
            )
            for r in raw_hits
        ]

        if not hits:
            return []

        hits = [h for h in hits if h.score >= self._rag_config.min_relevance_score]
        if not hits:
            logger.warning(
                "RAGService: all chunks below relevance threshold; returning []",
                extra={"query": query.text, "threshold": self._rag_config.min_relevance_score},
            )
            return []

        hits = _diversify(hits, top_k=query.top_k)

        if self._enable_reranking:
            try:
                return self._reranker.rerank(hits)
            except NotImplementedError:
                return hits

        return hits


def _diversify(hits: list[SearchResult], top_k: int) -> list[SearchResult]:
    """Round-robin interleave by document_id for result diversity."""
    buckets: dict[str, list[SearchResult]] = defaultdict(list)
    for hit in hits:
        buckets[hit.document_id].append(hit)

    result: list[SearchResult] = []
    doc_order = list(dict.fromkeys(h.document_id for h in hits))
    indices = {doc_id: 0 for doc_id in doc_order}

    while len(result) < top_k:
        advanced = False
        for doc_id in doc_order:
            if len(result) >= top_k:
                break
            idx = indices[doc_id]
            if idx < len(buckets[doc_id]):
                result.append(buckets[doc_id][idx])
                indices[doc_id] += 1
                advanced = True
        if not advanced:
            break

    return result
