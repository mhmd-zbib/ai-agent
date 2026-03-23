from datetime import UTC, datetime
from typing import cast

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError

from app.shared.schemas import MemoryEntry
from app.shared.logging import get_logger

logger = get_logger(__name__)


class LongTermRepository:
    """PostgreSQL-based repository for long-term message persistence with pagination support."""

    def __init__(self, engine: Engine, query_timeout_seconds: int = 30) -> None:
        """
        Initialize the long-term repository.

        Args:
            engine: SQLAlchemy engine with connection pooling
            query_timeout_seconds: Timeout for database queries
        """
        self._engine = engine
        self._query_timeout_seconds = query_timeout_seconds

    def ensure_schema(self) -> None:
        """Create database schema if it doesn't exist."""
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

    def get_messages(
        self,
        session_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """
        Retrieve messages for a session with optional pagination.

        Args:
            session_id: Unique session identifier
            limit: Maximum number of messages to retrieve (None for all)
            offset: Number of messages to skip (for pagination)

        Returns:
            List of messages ordered by message_index

        Note:
            Uses a single optimized query to avoid N+1 problems.
        """
        query = """
            SELECT role, content, created_at
            FROM chat_messages
            WHERE session_id = :session_id
            ORDER BY message_index ASC
        """

        params: dict[str, int | str] = {"session_id": session_id}

        if limit is not None:
            query += " LIMIT :limit OFFSET :offset"
            params["limit"] = limit
            params["offset"] = offset

        try:
            with self._engine.connect() as connection:
                # Set statement timeout for this connection
                connection.execute(
                    text(
                        f"SET LOCAL statement_timeout = '{self._query_timeout_seconds}s'"
                    )
                )

                rows = connection.execute(text(query), params).mappings()

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

        except TimeoutError as e:
            logger.error(
                "Database query timeout while fetching messages",
                extra={
                    "session_id": session_id,
                    "timeout_seconds": self._query_timeout_seconds,
                    "error": str(e),
                },
            )
            raise
        except OperationalError as e:
            logger.error(
                "Database operational error while fetching messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            raise
        except DBAPIError as e:
            logger.error(
                "Database error while fetching messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            raise

    def get_message_count(self, session_id: str) -> int:
        """
        Get the total number of messages for a session.

        Args:
            session_id: Unique session identifier

        Returns:
            Total count of messages
        """
        try:
            with self._engine.connect() as connection:
                connection.execute(
                    text(
                        f"SET LOCAL statement_timeout = '{self._query_timeout_seconds}s'"
                    )
                )

                count = connection.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM chat_messages
                        WHERE session_id = :session_id
                        """
                    ),
                    {"session_id": session_id},
                ).scalar_one()
                return int(count)

        except (TimeoutError, OperationalError, DBAPIError) as e:
            logger.error(
                "Database error while counting messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            raise

    def append_message(self, session_id: str, message: MemoryEntry) -> None:
        """
        Append a new message to a session.

        Args:
            session_id: Unique session identifier
            message: Message to append

        Note:
            Uses advisory locks to prevent race conditions when determining next index.
        """
        try:
            with self._engine.begin() as connection:
                # Set statement timeout for this transaction
                connection.execute(
                    text(
                        f"SET LOCAL statement_timeout = '{self._query_timeout_seconds}s'"
                    )
                )

                # Acquire advisory lock for this session
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:session_id))"),
                    {"session_id": session_id},
                )

                # Get current max index (single query, no N+1)
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

                # Insert new message
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

        except TimeoutError as e:
            logger.error(
                "Database query timeout while appending message",
                extra={
                    "session_id": session_id,
                    "timeout_seconds": self._query_timeout_seconds,
                    "error": str(e),
                },
            )
            raise
        except (OperationalError, DBAPIError) as e:
            logger.error(
                "Database error while appending message",
                extra={"session_id": session_id, "error": str(e)},
            )
            raise

    def clear(self, session_id: str) -> bool:
        """
        Clear all messages for a session.

        Args:
            session_id: Unique session identifier

        Returns:
            True if any messages were deleted, False otherwise
        """
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    text(
                        f"SET LOCAL statement_timeout = '{self._query_timeout_seconds}s'"
                    )
                )

                result = connection.execute(
                    text("DELETE FROM chat_messages WHERE session_id = :session_id"),
                    {"session_id": session_id},
                )
                return result.rowcount > 0

        except (TimeoutError, OperationalError, DBAPIError) as e:
            logger.error(
                "Database error while clearing messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            raise

    def close(self) -> None:
        """Dispose of the database engine and close all connections."""
        try:
            self._engine.dispose()
        except Exception as e:
            logger.error(
                "Error while disposing database engine",
                extra={"error": str(e)},
            )
