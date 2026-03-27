"""Ingest consumer — Stage 1 document parsing.

Delegates to the appropriate :class:`~ingestion.sources.base.BaseSource`
implementation based on the file extension and returns a
:class:`~shared.models.document.ParsedDocument`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from shared.models.document import ParsedDocument

from ingestion.sources.pdf import DocxSource, PdfSource

logger = logging.getLogger(__name__)

_PDF_EXTENSIONS = frozenset({".pdf"})
_DOCX_EXTENSIONS = frozenset({".epub", ".docx"})


class IngestConsumer:
    """Consume a raw document file and produce a :class:`ParsedDocument`.

    Selects the correct :class:`~ingestion.sources.base.BaseSource` based on
    the file extension:

    - ``.pdf`` → :class:`~ingestion.sources.pdf.PdfSource`
    - ``.epub`` / ``.docx`` → :class:`~ingestion.sources.pdf.DocxSource`

    Parameters
    ----------
    (none — sources are selected automatically by extension)
    """

    def __init__(self) -> None:
        self._pdf_source = PdfSource()
        self._docx_source = DocxSource()

    def run(
        self,
        file_path: str | Path,
        course_id: str,
        source_type: str = "textbook",
    ) -> ParsedDocument:
        """Parse *file_path* into a :class:`ParsedDocument`.

        Parameters
        ----------
        file_path:
            Absolute or relative path to the source file (PDF, EPUB, or DOCX).
        course_id:
            Identifier of the course this document belongs to.
        source_type:
            One of ``textbook``, ``slides``, ``lecture_notes``, ``exercises``.

        Returns
        -------
        ParsedDocument
            Structured, labelled document tree ready for chunking.

        Raises
        ------
        ValueError
            If the file extension is not supported.
        FileNotFoundError
            If *file_path* does not exist.
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        logger.info(
            "IngestConsumer.run",
            extra={"path": str(path), "ext": ext, "course_id": course_id},
        )

        if ext in _PDF_EXTENSIONS:
            return self._pdf_source.read(str(path), course_id, source_type)
        if ext in _DOCX_EXTENSIONS:
            return self._docx_source.read(str(path), course_id, source_type)

        raise ValueError(
            f"Unsupported file extension: {ext!r}. "
            f"Supported: {sorted(_PDF_EXTENSIONS | _DOCX_EXTENSIONS)}"
        )


__all__ = ["IngestConsumer"]
