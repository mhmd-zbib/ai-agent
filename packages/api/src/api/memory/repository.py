import json
from datetime import UTC, datetime
from typing import Any, cast

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError
from common.core.log_config import get_logger
from common.core.schemas import MemoryEntry
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError

logger = get_logger(__name__)


class ShortTermRepository:
    """Redis-based repository for short-term message caching with automatic TTL."""

    def __init__(self, redis_client: Redis, ttl_seconds: int) -> None:
        """
        Initialize the short-term repository.

        Args:
            redis_client: Redis client with connection pooling enabled
            ttl_seconds: Time-to-live for cached messages
        """
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(session_id: str) -> str:
        """Generate Redis key for a session."""
        return f"chat:session:{session_id}:messages"

    def _serialize_message(self, message: MemoryEntry) -> dict[str, str]:
        """Serialize a single message to JSON-compatible dict."""
        return {
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at.astimezone(UTC).isoformat(),
        }

    def _deserialize_message(self, data: dict[str, Any]) -> MemoryEntry:
        """Deserialize a message from JSON-compatible dict."""
        return MemoryEntry(
            role=data["role"],
            content=data["content"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def get_messages(self, session_id: str) -> list[MemoryEntry] | None:
        """
        Retrieve cached messages for a session.

        Args:
            session_id: Unique session identifier

        Returns:
            List of messages if cached, None if not found or on error
        """
        try:
            payload = self._redis.get(self._key(session_id))
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error during get",
                extra={"session_id": session_id, "error": str(e)},
            )
            return None
        except RedisError as e:
            logger.error(
                "Redis error during get_messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            return None

        if payload is None:
            return None

        try:
            raw_items: list[dict[str, Any]] = json.loads(payload)
            return [self._deserialize_message(item) for item in raw_items]
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(
                "Failed to deserialize cached messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            # Invalid cache entry, delete it
            self._safe_delete(session_id)
            return None

    def set_messages(self, session_id: str, messages: list[MemoryEntry]) -> bool:
        """
        Cache messages for a session with TTL.

        Args:
            session_id: Unique session identifier
            messages: List of messages to cache

        Returns:
            True if successfully cached, False otherwise
        """
        try:
            payload = json.dumps([self._serialize_message(msg) for msg in messages])
        except (TypeError, ValueError) as e:
            logger.error(
                "Failed to serialize messages for caching",
                extra={"session_id": session_id, "error": str(e)},
            )
            return False

        try:
            self._redis.set(self._key(session_id), payload, ex=self._ttl_seconds)
            return True
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error during set",
                extra={"session_id": session_id, "error": str(e)},
            )
            return False
        except RedisError as e:
            logger.error(
                "Redis error during set_messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            return False

    def delete_messages(self, session_id: str) -> bool:
        """
        Delete cached messages for a session.

        Args:
            session_id: Unique session identifier

        Returns:
            True if successfully deleted, False otherwise
        """
        return self._safe_delete(session_id)

    def _safe_delete(self, session_id: str) -> bool:
        """Internal method for safe deletion with error handling."""
        try:
            self._redis.delete(self._key(session_id))
            return True
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error during delete",
                extra={"session_id": session_id, "error": str(e)},
            )
            return False
        except RedisError as e:
            logger.error(
                "Redis error during delete_messages",
                extra={"session_id": session_id, "error": str(e)},
            )
            return False

    @staticmethod
    def _metadata_key(session_id: str, key: str) -> str:
        """Generate Redis key for session metadata."""
        return f"chat:session:{session_id}:metadata:{key}"

    def get_metadata(self, session_id: str, key: str) -> str | None:
        """
        Retrieve a metadata value for a session.

        Args:
            session_id: Unique session identifier
            key: Metadata key (e.g., "course_code")

        Returns:
            Metadata value as string if found, None otherwise
        """
        try:
            value = self._redis.get(self._metadata_key(session_id, key))
            return value if value else None
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error during get_metadata",
                extra={"session_id": session_id, "key": key, "error": str(e)},
            )
            return None
        except RedisError as e:
            logger.error(
                "Redis error during get_metadata",
                extra={"session_id": session_id, "key": key, "error": str(e)},
            )
            return None

    def set_metadata(self, session_id: str, key: str, value: str) -> bool:
        """
        Set a metadata value for a session with TTL.

        Args:
            session_id: Unique session identifier
            key: Metadata key (e.g., "course_code")
            value: Metadata value to store

        Returns:
            True if successfully set, False otherwise
        """
        try:
            self._redis.set(
                self._metadata_key(session_id, key), value, ex=self._ttl_seconds
            )
            return True
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error during set_metadata",
                extra={"session_id": session_id, "key": key, "error": str(e)},
            )
            return False
        except RedisError as e:
            logger.error(
                "Redis error during set_metadata",
                extra={"session_id": session_id, "key": key, "error": str(e)},
            )
            return False

    def delete_metadata(self, session_id: str, key: str) -> bool:
        """
        Delete a metadata value for a session.

        Args:
            session_id: Unique session identifier
            key: Metadata key to delete

        Returns:
            True if successfully deleted, False otherwise
        """
        try:
            self._redis.delete(self._metadata_key(session_id, key))
            return True
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(
                "Redis connection/timeout error during delete_metadata",
                extra={"session_id": session_id, "key": key, "error": str(e)},
            )
            return False
        except RedisError as e:
            logger.error(
                "Redis error during delete_metadata",
                extra={"session_id": session_id, "key": key, "error": str(e)},
            )
            return False


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
