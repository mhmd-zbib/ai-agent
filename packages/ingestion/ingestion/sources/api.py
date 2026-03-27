"""HTTP API document source stub.

Fetches raw course content from a remote HTTP API endpoint and produces
a :class:`~shared.models.document.ParsedDocument` for downstream processing.

Not yet implemented — extend :class:`BaseSource` here when an API-backed
ingestion flow is needed.
"""

from __future__ import annotations

from shared.models.document import ParsedDocument

from ingestion.sources.base import BaseSource


class ApiSource(BaseSource):
    """Fetch a document from a remote HTTP API.

    Parameters
    ----------
    base_url:
        Base URL of the API, e.g. ``https://lms.example.com/api/v1``.
    api_key:
        Bearer token or API key used for authentication.
    """

    def __init__(self, base_url: str, api_key: str = "") -> None:
        self._base_url = base_url
        self._api_key = api_key

    def read(self, path: str, course_id: str, source_type: str = "textbook") -> ParsedDocument:
        """Not implemented — raises :exc:`NotImplementedError`.

        path is interpreted as the API resource path, e.g. ``/courses/CS101/content``.
        """
        raise NotImplementedError(
            "ApiSource.read() is not yet implemented. "
            "path is the API resource path relative to base_url."
        )


__all__ = ["ApiSource"]
