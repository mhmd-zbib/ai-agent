"""PDF and DOCX document source adapters.

Migrated from pipeline.ingestion.stage1_parser (Stage 1 — Document Restructuring).

Parses raw book files (PDF, EPUB, DOCX) into a labelled element tree.
Every element is classified by type before any chunking occurs.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from common.models.document import (
    ATOMIC_ELEMENT_TYPES,
    Chapter,
    DocumentElement,
    ParsedDocument,
    Section,
)

logger = logging.getLogger(__name__)

_SUPPORTED_PDF_EXTENSIONS = frozenset({".pdf"})
_SUPPORTED_DOCX_EXTENSIONS = frozenset({".epub", ".docx"})
_SUPPORTED_EXTENSIONS = _SUPPORTED_PDF_EXTENSIONS | _SUPPORTED_DOCX_EXTENSIONS
_SOURCE_TYPES = frozenset({"textbook", "slides", "lecture_notes", "exercises"})


# ──────────────────────────────────────────────────────────────────────────────
# BaseSource (inlined from sources/base.py)
# ──────────────────────────────────────────────────────────────────────────────


class BaseSource(ABC):
    """Read a file at *path* and return a structured :class:`ParsedDocument`.

    Subclasses implement format-specific parsing (PDF, DOCX, EPUB, etc.).
    The rest of the pipeline is format-agnostic and works exclusively with
    :class:`~core.models.document.ParsedDocument`.
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


# ──────────────────────────────────────────────────────────────────────────────
# PdfSource
# ──────────────────────────────────────────────────────────────────────────────


class PdfSource(BaseSource):
    """Parse PDF files using docling (primary) with pymupdf as fallback."""

    def read(self, path: str, course_id: str, source_type: str = "textbook") -> ParsedDocument:
        """Parse a PDF file into a :class:`ParsedDocument`.

        Parameters
        ----------
        path:
            Absolute or relative path to the PDF file.
        course_id:
            Identifier of the course this document belongs to.
        source_type:
            One of ``textbook``, ``slides``, ``lecture_notes``, ``exercises``.

        Returns
        -------
        ParsedDocument
            Structured, labelled document tree ready for chunking.
        """
        file_path = Path(path)
        _validate_file(file_path, _SUPPORTED_PDF_EXTENSIONS, source_type)

        logger.info(
            "Parsing PDF document",
            extra={"path": str(file_path), "course_id": course_id},
        )

        elements = _parse_pdf(file_path)
        doc = _build_document_tree(elements, course_id, source_type)

        logger.info(
            "PDF parsed",
            extra={
                "course_id": course_id,
                "chapters": len(doc.chapters),
                "elements": sum(
                    len(s.elements) for ch in doc.chapters for s in ch.sections
                ),
            },
        )
        return doc


# ──────────────────────────────────────────────────────────────────────────────
# DocxSource
# ──────────────────────────────────────────────────────────────────────────────


class DocxSource(BaseSource):
    """Parse EPUB and DOCX files using the unstructured library."""

    def read(self, path: str, course_id: str, source_type: str = "textbook") -> ParsedDocument:
        """Parse a DOCX or EPUB file into a :class:`ParsedDocument`.

        Parameters
        ----------
        path:
            Absolute or relative path to the DOCX or EPUB file.
        course_id:
            Identifier of the course this document belongs to.
        source_type:
            One of ``textbook``, ``slides``, ``lecture_notes``, ``exercises``.

        Returns
        -------
        ParsedDocument
            Structured, labelled document tree ready for chunking.
        """
        file_path = Path(path)
        _validate_file(file_path, _SUPPORTED_DOCX_EXTENSIONS, source_type)

        logger.info(
            "Parsing DOCX/EPUB document",
            extra={"path": str(file_path), "course_id": course_id},
        )

        elements = _parse_with_unstructured(file_path)
        doc = _build_document_tree(elements, course_id, source_type)

        logger.info(
            "DOCX/EPUB parsed",
            extra={
                "course_id": course_id,
                "chapters": len(doc.chapters),
                "elements": sum(
                    len(s.elements) for ch in doc.chapters for s in ch.sections
                ),
            },
        )
        return doc


# ──────────────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────────────


def _validate_file(
    path: Path,
    allowed_extensions: frozenset[str],
    source_type: str,
) -> None:
    """Raise if file does not exist, has wrong extension, or source_type is invalid."""
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    ext = path.suffix.lower()
    if ext not in allowed_extensions:
        raise ValueError(
            f"Unsupported file type: {ext!r}. Supported: {allowed_extensions}"
        )

    if source_type not in _SOURCE_TYPES:
        raise ValueError(
            f"Invalid source_type: {source_type!r}. Must be one of {_SOURCE_TYPES}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# PDF Parsing — docling primary, pymupdf fallback
# ──────────────────────────────────────────────────────────────────────────────


def _parse_pdf(path: Path) -> list[tuple[str, str, str | None]]:
    """Return a flat list of (element_type, text, language) tuples for a PDF."""
    try:
        return _parse_pdf_docling(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "docling failed, falling back to pymupdf",
            extra={"path": str(path), "error": str(exc)},
        )
        return _parse_pdf_pymupdf(path)


def _parse_pdf_docling(path: Path) -> list[tuple[str, str, str | None]]:
    """Parse PDF with docling (preferred for academic/textbook PDFs)."""
    from docling.document_converter import DocumentConverter  # type: ignore[import-untyped]

    converter = DocumentConverter()
    result = converter.convert(str(path))
    doc = result.document

    elements: list[tuple[str, str, str | None]] = []
    for item, _level in doc.iterate_items():
        label = _docling_label_to_element_type(item)
        text = _docling_item_text(item)
        if text.strip():
            elements.append((label, text.strip(), None))
    return elements


def _docling_label_to_element_type(item: object) -> str:
    """Map a docling document item to our element type vocabulary."""
    from docling.datamodel.document import (  # type: ignore[import-untyped]
        PictureItem,
        TableItem,
    )
    from docling_core.types.doc import DocItemLabel  # type: ignore[import-untyped]

    if isinstance(item, TableItem):
        return "table"
    if isinstance(item, PictureItem):
        return "figure_caption"

    label = getattr(item, "label", None)
    if label is None:
        return "paragraph"

    _MAP: dict[str, str] = {
        DocItemLabel.TITLE: "heading_h1",
        DocItemLabel.SECTION_HEADER: "heading_h2",
        DocItemLabel.PARAGRAPH: "paragraph",
        DocItemLabel.TEXT: "paragraph",
        DocItemLabel.CODE: "code",
        DocItemLabel.TABLE: "table",
        DocItemLabel.LIST_ITEM: "list",
        DocItemLabel.FORMULA: "math",
        DocItemLabel.CAPTION: "figure_caption",
        DocItemLabel.FOOTNOTE: "paragraph",
        DocItemLabel.PAGE_HEADER: "heading_h3",
        DocItemLabel.PAGE_FOOTER: "paragraph",
    }
    return _MAP.get(label, "paragraph")


def _docling_item_text(item: object) -> str:
    """Extract plain text from a docling item, handling tables specially."""
    from docling.datamodel.document import TableItem  # type: ignore[import-untyped]

    if isinstance(item, TableItem):
        return _table_to_markdown(item)
    text = getattr(item, "text", None)
    if text:
        return str(text)
    export = getattr(item, "export_to_markdown", None)
    if callable(export):
        return str(export())
    return ""


def _table_to_markdown(table_item: object) -> str:
    """Serialize a docling TableItem to pipe-delimited markdown."""
    try:
        export = getattr(table_item, "export_to_dataframe", None)
        if callable(export):
            df = export()
            rows = [df.columns.tolist()] + df.values.tolist()
            lines = []
            for i, row in enumerate(rows):
                lines.append("| " + " | ".join(str(c) for c in row) + " |")
                if i == 0:
                    lines.append("|" + "|".join("---" for _ in row) + "|")
            return "\n".join(lines)
    except Exception:  # noqa: BLE001
        pass
    markdown = getattr(table_item, "export_to_markdown", None)
    if callable(markdown):
        return str(markdown())
    return str(table_item)


def _parse_pdf_pymupdf(path: Path) -> list[tuple[str, str, str | None]]:
    """Fallback PDF parser using pymupdf (fitz). Heuristic classification only."""
    import fitz  # type: ignore[import-untyped]  # pymupdf

    doc = fitz.open(str(path))
    elements: list[tuple[str, str, str | None]] = []

    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block.get("type") != 0:  # 0 = text block
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    size = span.get("size", 12)
                    flags = span.get("flags", 0)
                    is_bold = bool(flags & 2**4)
                    label = _pymupdf_classify(text, size, is_bold)
                    elements.append((label, text, None))

    doc.close()
    return elements


def _pymupdf_classify(text: str, font_size: float, is_bold: bool) -> str:
    """Heuristic classification for pymupdf spans."""
    if font_size >= 20 or (is_bold and font_size >= 16):
        return "heading_h1"
    if font_size >= 16 or (is_bold and font_size >= 14):
        return "heading_h2"
    if font_size >= 14 or is_bold:
        return "heading_h3"
    if text.startswith("    ") or text.startswith("\t"):
        return "code"
    return "paragraph"


# ──────────────────────────────────────────────────────────────────────────────
# EPUB / DOCX Parsing — unstructured
# ──────────────────────────────────────────────────────────────────────────────


def _parse_with_unstructured(path: Path) -> list[tuple[str, str, str | None]]:
    """Parse EPUB or DOCX using the unstructured library."""
    from unstructured.partition.auto import partition  # type: ignore[import-untyped]

    elements = partition(filename=str(path))
    result: list[tuple[str, str, str | None]] = []
    for el in elements:
        label = _unstructured_type_to_element_type(type(el).__name__)
        text = str(el).strip()
        if text:
            result.append((label, text, None))
    return result


def _unstructured_type_to_element_type(type_name: str) -> str:
    """Map unstructured element class names to our vocabulary."""
    _MAP: dict[str, str] = {
        "Title": "heading_h1",
        "Header": "heading_h2",
        "NarrativeText": "paragraph",
        "Text": "paragraph",
        "CodeSnippet": "code",
        "Table": "table",
        "ListItem": "list",
        "Formula": "math",
        "FigureCaption": "figure_caption",
        "Footer": "paragraph",
        "PageBreak": "paragraph",
        "EmailAddress": "paragraph",
        "Image": "figure_caption",
    }
    return _MAP.get(type_name, "paragraph")


# ──────────────────────────────────────────────────────────────────────────────
# Structure Analyzer — builds the document tree from flat element list
# ──────────────────────────────────────────────────────────────────────────────


def _build_document_tree(
    flat_elements: list[tuple[str, str, str | None]],
    course_id: str,
    source_type: str,
) -> ParsedDocument:
    """Convert a flat (type, text, lang) list into a ParsedDocument tree.

    Strategy
    --------
    - H1 headings start a new Chapter.
    - H2/H3 headings start a new Section within the current Chapter.
    - All other elements are appended to the current Section.
    - A synthetic Chapter 0 / Section 0 captures any content before the first heading.
    """
    chapters: list[Chapter] = []
    current_chapter: Chapter | None = None
    current_section: Section | None = None
    chapter_idx = 0
    section_idx = 0

    def _ensure_chapter(title: str = "Untitled") -> Chapter:
        nonlocal chapter_idx, section_idx
        ch = Chapter(chapter=chapter_idx, title=title)
        chapters.append(ch)
        chapter_idx += 1
        section_idx = 0
        return ch

    def _ensure_section(title: str = "Untitled") -> Section:
        nonlocal section_idx
        assert current_chapter is not None
        sec = Section(section=section_idx, title=title)
        current_chapter.sections.append(sec)
        section_idx += 1
        return sec

    for el_type, text, lang in flat_elements:
        if el_type == "heading_h1":
            current_chapter = _ensure_chapter(text)
            current_section = _ensure_section("Introduction")
        elif el_type in ("heading_h2", "heading_h3"):
            if current_chapter is None:
                current_chapter = _ensure_chapter("Introduction")
            current_section = _ensure_section(text)
        else:
            if current_chapter is None:
                current_chapter = _ensure_chapter("Introduction")
            if current_section is None:
                current_section = _ensure_section("Introduction")
            element = DocumentElement(type=el_type, text=text, language=lang)
            current_section.elements.append(element)

    # Remove empty chapters/sections
    for ch in chapters:
        ch.sections = [s for s in ch.sections if s.elements]
    chapters = [ch for ch in chapters if ch.sections]

    # If nothing parsed, return a minimal valid document
    if not chapters:
        dummy_ch = Chapter(chapter=0, title="Document")
        dummy_sec = Section(section=0, title="Content")
        dummy_ch.sections.append(dummy_sec)
        chapters = [dummy_ch]

    return ParsedDocument(
        course_id=course_id, source_type=source_type, chapters=chapters
    )


# Re-export ATOMIC_ELEMENT_TYPES so callers can inspect atomicity.
__all__ = [
    "ATOMIC_ELEMENT_TYPES",
    "BaseSource",
    "DocxSource",
    "PdfSource",
]
