from pydantic import BaseModel


class SearchQuery(BaseModel):
    text: str
    top_k: int = 5


class SearchResult(BaseModel):
    chunk_id: str
    score: float
    text: str

