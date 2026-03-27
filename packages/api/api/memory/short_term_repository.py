import json
from datetime import UTC, datetime
from typing import Any

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError
from shared.logging import get_logger
from shared.schemas import MemoryEntry

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
