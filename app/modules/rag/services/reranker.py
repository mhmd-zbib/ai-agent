from app.modules.rag.schemas import SearchResult


class Reranker:
    def rerank(self, items: list[SearchResult]) -> list[SearchResult]:
        return items

