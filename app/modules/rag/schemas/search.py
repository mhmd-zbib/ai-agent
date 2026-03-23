from pydantic import BaseModel


class SearchQuery(BaseModel):
    text: str
    top_k: int = 5
    user_id: str = ""
    course_code: str = ""
    university_name: str = ""


class SearchResult(BaseModel):
    chunk_id: str
    score: float
    text: str
    source: str = ""
    document_id: str = ""
