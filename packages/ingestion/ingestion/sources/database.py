"""Database document source stub.

Reads structured course content from a relational database and produces
a :class:`~shared.models.document.ParsedDocument` for downstream processing.

Not yet implemented — extend :class:`BaseSource` here when a DB-backed
ingestion flow is needed.
"""

from __future__ import annotations

from shared.models.document import ParsedDocument

from ingestion.sources.base import BaseSource


class DatabaseSource(BaseSource):
    """Fetch a document from a relational database.

    Parameters
    ----------
    dsn:
        asyncpg-compatible connection string, e.g.
        ``postgresql://user:pass@host/db``.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def read(self, path: str, course_id: str, source_type: str = "textbook") -> ParsedDocument:
        """Not implemented — raises :exc:`NotImplementedError`."""
        raise NotImplementedError(
            "DatabaseSource.read() is not yet implemented. "
            "path is interpreted as a document identifier (e.g. UUID or slug)."
        )


__all__ = ["DatabaseSource"]
