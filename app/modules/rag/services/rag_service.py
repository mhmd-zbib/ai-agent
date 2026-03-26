import logging
from collections import defaultdict

from app.modules.rag.schemas import SearchQuery, SearchResult
from app.modules.rag.services.base_reranker import BaseReranker
from app.shared.config import RagConfig
from app.shared.protocols import IEmbeddingClient, IVectorClient

logger = logging.getLogger(__name__)


class RAGService:
    """
    Retrieval-Augmented Generation service.

    Orchestrates the retrieval pipeline:
    1. Embed the query
    2. Vector similarity search (over-fetch for diversity)
    3. Interleave results across documents so every document gets a slot
    4. Optional reranking for relevance
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
        """
        Perform retrieval search with optional reranking.

        The filtering and retrieval process follows this order:
        1. Namespace filter (user_id) - ALWAYS applied to isolate user's documents
        2. Metadata filters (course_code, university_name) - applied if provided
        3. Semantic search within the filtered subset using query embedding
        4. Relevance threshold filtering (>= 0.40 cosine similarity)
        5. Diversity filtering - round-robin across documents to ensure variety

        Args:
            query: Search query with text, user_id, and top_k

        Returns:
            List of search results, reranked if enabled
        """
        if self._vector_client is None or self._embedding_client is None:
            logger.warning(
                "RAGService: vector or embedding client not configured; returning []"
            )
            return []

        logger.info(
            "RAGService: searching", extra={"query": query.text, "top_k": query.top_k}
        )

        try:
            payload_filter: dict[str, str] = {}
            if query.course_code:
                payload_filter["course_code"] = query.course_code
            if query.university_name:
                payload_filter["university_name"] = query.university_name

            # Log filter conditions being applied
            logger.debug(
                "RAGService: applying filters",
                extra={
                    "namespace": query.user_id,
                    "course_code": query.course_code or "not_specified",
                    "university_name": query.university_name or "not_specified",
                    "fetch_k": query.top_k * self._rag_config.fetch_multiplier,
                },
            )

            vector = self._embedding_client.embed(query.text)
            # Over-fetch so the diversity step has enough candidates from all docs.
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
            logger.info(
                "RAGService: no results found after vector search",
                extra={
                    "query": query.text,
                    "course_code": query.course_code or "not_specified",
                    "university_name": query.university_name or "not_specified",
                },
            )
            return []

        # Drop chunks that are not relevant enough to be useful.
        # These would cause the reasoning agent to hallucinate from weak matches.
        initial_count = len(hits)
        hits = [h for h in hits if h.score >= self._rag_config.min_relevance_score]
        
        if initial_count > len(hits):
            logger.debug(
                "RAGService: filtered by relevance threshold",
                extra={
                    "initial_count": initial_count,
                    "filtered_count": len(hits),
                    "threshold": self._rag_config.min_relevance_score,
                },
            )
        
        if not hits:
            logger.warning(
                "RAGService: all chunks below relevance threshold; returning []",
                extra={
                    "query": query.text,
                    "threshold": self._rag_config.min_relevance_score,
                    "course_code": query.course_code or "not_specified",
                },
            )
            return []

        hits = _diversify(hits, top_k=query.top_k)
        
        logger.debug(
            "RAGService: search completed",
            extra={"results_count": len(hits), "query": query.text},
        )

        if self._enable_reranking:
            try:
                return self._reranker.rerank(hits)
            except NotImplementedError:
                logger.debug(
                    "RAGService: reranker not implemented, returning raw results"
                )
                return hits

        return hits


def _diversify(hits: list[SearchResult], top_k: int) -> list[SearchResult]:
    """
    Round-robin interleave by document_id so that every document contributes
    at least one chunk before any document gets a second slot.

    Hits arrive pre-sorted by score (descending) from the vector DB.
    Within each document the original score order is preserved.
    """
    buckets: dict[str, list[SearchResult]] = defaultdict(list)
    for hit in hits:
        buckets[hit.document_id].append(hit)

    result: list[SearchResult] = []
    # Cycle through docs in the order their best chunk appeared (score-ordered)
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
            break  # all buckets exhausted

    return result
