from datetime import UTC, datetime
from typing import cast

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.modules.memory.schemas import MemoryEntry


class LongTermRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_schema(self) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id BIGSERIAL PRIMARY KEY,
                        session_id VARCHAR(128) NOT NULL,
                        message_index INTEGER NOT NULL,
                        role VARCHAR(16) NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
                        content TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE (session_id, message_index)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chat_messages_session_order
                    ON chat_messages (session_id, message_index)
                    """
                )
            )

    def get_messages(self, session_id: str) -> list[MemoryEntry]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT role, content, created_at
                    FROM chat_messages
                    WHERE session_id = :session_id
                    ORDER BY message_index ASC
                    """
                ),
                {"session_id": session_id},
            ).mappings()

        messages: list[MemoryEntry] = []
        for row in rows:
            created_at = row["created_at"] or datetime.now(UTC)
            messages.append(
                MemoryEntry(
                    role=cast(str, row["role"]),
                    content=str(row["content"]),
                    created_at=created_at,
                )
            )
        return messages

    def append_message(self, session_id: str, message: MemoryEntry) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:session_id))"),
                {"session_id": session_id},
            )
            current_max = connection.execute(
                text(
                    """
                    SELECT COALESCE(MAX(message_index), -1)
                    FROM chat_messages
                    WHERE session_id = :session_id
                    """
                ),
                {"session_id": session_id},
            ).scalar_one()
            next_index = int(current_max) + 1

            connection.execute(
                text(
                    """
                    INSERT INTO chat_messages (session_id, message_index, role, content, created_at)
                    VALUES (:session_id, :message_index, :role, :content, :created_at)
                    """
                ),
                {
                    "session_id": session_id,
                    "message_index": next_index,
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at,
                },
            )

    def clear(self, session_id: str) -> bool:
        with self._engine.begin() as connection:
            result = connection.execute(
                text("DELETE FROM chat_messages WHERE session_id = :session_id"),
                {"session_id": session_id},
            )
        return result.rowcount > 0

    def close(self) -> None:
        self._engine.dispose()

