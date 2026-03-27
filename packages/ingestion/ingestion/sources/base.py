"""Abstract base class for all document sources."""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared.models.document import ParsedDocument


class BaseSource(ABC):
    """Read a file at *path* and return a structured :class:`ParsedDocument`.

    Subclasses implement format-specific parsing (PDF, DOCX, EPUB, etc.).
    The rest of the pipeline is format-agnostic and works exclusively with
    :class:`~shared.models.document.ParsedDocument`.
    """

    @abstractmethod
    def read(self, path: str, course_id: str, source_type: str = "textbook") -> ParsedDocument:
        """Parse the file at *path* into a :class:`ParsedDocument`.

        Parameters
        ----------
        path:
            Absolute or relative path to the source file.
        course_id:
            Identifier of the course this document belongs to.
        source_type:
            One of ``textbook``, ``slides``, ``lecture_notes``, ``exercises``.

        Returns
        -------
        ParsedDocument
            Structured, labelled document tree ready for chunking.
        """
        ...


__all__ = ["BaseSource"]
