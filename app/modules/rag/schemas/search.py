from pydantic import BaseModel


class SearchQuery(BaseModel):
    text: str
    top_k: int = 5
    user_id: str = ""


class SearchResult(BaseModel):
    chunk_id: str
    score: float
    text: str

