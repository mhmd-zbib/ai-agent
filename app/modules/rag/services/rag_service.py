import logging

from app.modules.rag.schemas import SearchQuery, SearchResult
from app.modules.rag.services.base_reranker import BaseReranker
from app.shared.protocols import IEmbeddingClient, IVectorClient

logger = logging.getLogger(__name__)


class RAGService:
    """
    Retrieval-Augmented Generation service.

    Orchestrates the retrieval pipeline:
    1. Embed the query
    2. Vector similarity search
    3. Optional reranking for relevance
    """

    def __init__(
        self,
        vector_client: IVectorClient | None,
        embedding_client: IEmbeddingClient | None,
        reranker: BaseReranker,
        enable_reranking: bool = True,
    ) -> None:
        self._vector_client = vector_client
        self._embedding_client = embedding_client
        self._reranker = reranker
        self._enable_reranking = enable_reranking

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """
        Perform retrieval search with optional reranking.

        Args:
            query: Search query with text, user_id, and top_k

        Returns:
            List of search results, reranked if enabled
        """
        if self._vector_client is None or self._embedding_client is None:
            logger.warning("RAGService: vector or embedding client not configured; returning []")
            return []

        logger.info("RAGService: searching", extra={"query": query.text, "top_k": query.top_k})

        try:
            vector = self._embedding_client.embed(query.text)
            raw_hits = self._vector_client.query(
                vector=vector,
                top_k=query.top_k,
                namespace=query.user_id,
            )
        except Exception as exc:
            logger.error("RAGService: vector search failed", extra={"error": str(exc)})
            raise RuntimeError(f"Search failed for query: {query.text}") from exc

        hits = [
            SearchResult(
                chunk_id=str(r.get("id", "")),
                score=float(r.get("score", 0.0)),
                text=str((r.get("metadata") or {}).get("text", "")),
                source=str((r.get("metadata") or {}).get("source", "")),
            )
            for r in raw_hits
        ]

        if not hits:
            return []

        if self._enable_reranking:
            try:
                return self._reranker.rerank(hits)
            except NotImplementedError:
                logger.debug("RAGService: reranker not implemented, returning raw results")
                return hits

        return hits
