from app.modules.rag.schemas import SearchQuery, SearchResult


class VectorRepository:
    def search(self, query: SearchQuery) -> list[SearchResult]:
        return []

    def upsert(self, embeddings: list[dict[str, object]]) -> None:
        return

