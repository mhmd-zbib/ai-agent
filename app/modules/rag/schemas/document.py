from pydantic import BaseModel


class Document(BaseModel):
    id: str
    title: str
    content: str


class Chunk(BaseModel):
    id: str
    document_id: str
    text: str

