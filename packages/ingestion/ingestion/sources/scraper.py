"""Web scraper document source stub.

Scrapes course content from a public web page and produces a
:class:`~shared.models.document.ParsedDocument` for downstream processing.

Not yet implemented — extend :class:`BaseSource` here when a web-scraping
ingestion flow is needed.
"""

from __future__ import annotations

from shared.models.document import ParsedDocument

from ingestion.sources.base import BaseSource


class ScraperSource(BaseSource):
    """Scrape structured content from a web page.

    Parameters
    ----------
    timeout:
        HTTP request timeout in seconds (default: 30).
    user_agent:
        Custom User-Agent header sent with every request.
    """

    def __init__(
        self,
        timeout: int = 30,
        user_agent: str = "IngestionBot/1.0",
    ) -> None:
        self._timeout = timeout
        self._user_agent = user_agent

    def read(self, path: str, course_id: str, source_type: str = "textbook") -> ParsedDocument:
        """Not implemented — raises :exc:`NotImplementedError`.

        path is interpreted as a fully-qualified URL to scrape,
        e.g. ``https://example.com/course/chapter1``.
        """
        raise NotImplementedError(
            "ScraperSource.read() is not yet implemented. "
            "path must be a fully-qualified URL."
        )


__all__ = ["ScraperSource"]
