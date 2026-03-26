"""Document lifecycle and state transition management."""

from app.shared.logging import get_logger

logger = get_logger(__name__)


class DocumentLifecycle:
    """Manages valid document state transitions."""

    # Define valid state machine transitions
    TRANSITIONS: dict[str, list[str]] = {
        "uploaded": ["parsing", "failed"],
        "parsing": ["parsed", "failed"],
        "parsed": ["chunking", "failed"],
        "chunking": ["chunked", "failed"],
        "chunked": ["embedding", "failed"],
        "embedding": ["embedded", "failed"],
        "embedded": ["storing", "failed"],
        "storing": ["completed", "failed"],
        "completed": [],  # terminal state
        "failed": [],  # terminal state
    }

    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        """Check if transition from one status to another is valid."""
        valid_transitions = cls.TRANSITIONS.get(from_status, [])
        return to_status in valid_transitions

    @classmethod
    def validate_transition(cls, from_status: str, to_status: str) -> None:
        """Validate transition, raise exception if invalid."""
        if not cls.can_transition(from_status, to_status):
            raise InvalidStateTransitionError(
                f"Cannot transition from '{from_status}' to '{to_status}'"
            )

    @classmethod
    def get_next_states(cls, current_status: str) -> list[str]:
        """Get list of valid next states."""
        return cls.TRANSITIONS.get(current_status, [])


class InvalidStateTransitionError(Exception):
    """Raised when attempting an invalid state transition."""

    pass
