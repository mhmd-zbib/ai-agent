from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, str] = Field(default_factory=dict)


class ToolResult(BaseModel):
    name: str
    output: str


class AgentOutput(BaseModel):
    message: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
