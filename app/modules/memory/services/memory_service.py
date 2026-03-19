from app.modules.memory.repositories import LongTermRepository, ShortTermRepository
from app.modules.memory.schemas import MemoryEntry, SessionState


class MemoryService:
    def __init__(
        self,
        short_term_repository: ShortTermRepository,
        long_term_repository: LongTermRepository,
    ) -> None:
        self._short_term_repository = short_term_repository
        self._long_term_repository = long_term_repository

    def get_session_state(self, session_id: str) -> SessionState:
        cached = self._short_term_repository.get_messages(session_id)
        if cached is not None:
            return SessionState(session_id=session_id, messages=cached)

        persisted = self._long_term_repository.get_messages(session_id)
        self._short_term_repository.set_messages(session_id, persisted)
        return SessionState(session_id=session_id, messages=persisted)

    def append_message(self, session_id: str, entry: MemoryEntry) -> None:
        self._long_term_repository.append_message(session_id, entry)
        refreshed = self._long_term_repository.get_messages(session_id)
        self._short_term_repository.set_messages(session_id, refreshed)

    def clear_session(self, session_id: str) -> bool:
        cleared = self._long_term_repository.clear(session_id)
        self._short_term_repository.delete_messages(session_id)
        return cleared

    def close(self) -> None:
        self._long_term_repository.close()

