from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    user_message: str = Field(min_length=1, max_length=8000)
    session_id: str
    history: list[dict[str, str]]

