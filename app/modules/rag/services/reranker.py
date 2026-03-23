from app.modules.rag.schemas import SearchResult
from app.modules.rag.services.base_reranker import BaseReranker


class Reranker(BaseReranker):
    """
    Default reranker implementation (stub).

    This is a placeholder implementation that should be replaced with
    a real reranking algorithm (e.g., cross-encoder based reranking,
    diversity-based reranking, or relevance score adjustment).

    Raises:
        NotImplementedError: This is a stub implementation
    """

    def rerank(self, items: list[SearchResult]) -> list[SearchResult]:
        """
        Stub implementation - raises NotImplementedError.

        Real implementation should:
        - Score items based on relevance to query
        - Apply diversity filtering
        - Adjust ranking based on business rules

        Args:
            items: Search results to rerank

        Returns:
            Reranked search results

        Raises:
            NotImplementedError: Reranking not yet implemented
        """
        raise NotImplementedError(
            "Reranker is a stub. Implement with cross-encoder model or other "
            "reranking strategy. To bypass reranking, use PassthroughReranker."
        )


class PassthroughReranker(BaseReranker):
    """Reranker that passes items through without modification (for testing/fallback)."""

    def rerank(self, items: list[SearchResult]) -> list[SearchResult]:
        """Return items unchanged."""
        return items


class ScoreBasedReranker(BaseReranker):
    """Simple reranker that sorts by score in descending order."""

    def rerank(self, items: list[SearchResult]) -> list[SearchResult]:
        """Sort items by score in descending order."""
        return sorted(items, key=lambda x: x.score, reverse=True)
