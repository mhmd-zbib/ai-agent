from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


Role = Literal["system", "user", "assistant"]


@dataclass(slots=True)
class MemoryEntry:
    role: Role
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class SessionState:
    session_id: str
    messages: list[MemoryEntry]

