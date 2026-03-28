"""Structure-aware chunker transform.

Migrated from pipeline.ingestion.stage2_chunker (Stage 2 — Structure-Aware Chunking).

Splits a ParsedDocument into chunks that:
- Never cross section or chapter boundaries
- Never split atomic elements (code, table, math)
- Target 256-512 tokens (soft limit; atomic units may exceed this)
- Apply 15% token overlap between consecutive chunks in the same section
"""

from __future__ import annotations

import logging

import tiktoken
from common.models.document import (
    ATOMIC_ELEMENT_TYPES,
    HEADING_ELEMENT_TYPES,
    Chapter,
    Chunk,
    DocumentElement,
    ParsedDocument,
    Section,
)

logger = logging.getLogger(__name__)

# Token budget constants
_TARGET_MIN_TOKENS = 256
_TARGET_MAX_TOKENS = 512
_OVERLAP_FRACTION = 0.15  # 15% overlap
_ENCODING_NAME = "cl100k_base"

_enc = tiktoken.get_encoding(_ENCODING_NAME)


def _count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def _overlap_tokens(text: str, fraction: float) -> str:
    """Return the last *fraction* of *text* measured in tokens."""
    tokens = _enc.encode(text)
    n = max(1, int(len(tokens) * fraction))
    return _enc.decode(tokens[-n:])


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


def chunk_document(doc: ParsedDocument) -> list[Chunk]:
    """Chunk a :class:`ParsedDocument` into a flat list of :class:`Chunk` objects.

    Parameters
    ----------
    doc:
        Fully parsed document from Stage 1.

    Returns
    -------
    list[Chunk]
        Ordered chunks ready for Stage 3 metadata generation.
    """
    all_chunks: list[Chunk] = []
    for chapter in doc.chapters:
        chapter_chunks = _chunk_chapter(chapter, doc.course_id)
        all_chunks.extend(chapter_chunks)

    logger.info(
        "Chunking complete",
        extra={"course_id": doc.course_id, "total_chunks": len(all_chunks)},
    )
    return all_chunks


# ──────────────────────────────────────────────────────────────────────────────
# Chapter / Section processing
# ──────────────────────────────────────────────────────────────────────────────


def _chunk_chapter(chapter: Chapter, course_id: str) -> list[Chunk]:
    """Produce all chunks for one chapter. Chunks never cross chapter boundary."""
    chapter_chunks: list[Chunk] = []
    for section in chapter.sections:
        section_chunks = _chunk_section(section, chapter, course_id)
        chapter_chunks.extend(section_chunks)
    return chapter_chunks


def _chunk_section(section: Section, chapter: Chapter, course_id: str) -> list[Chunk]:
    """Produce all chunks for one section. Chunks never cross section boundary."""
    chunks: list[Chunk] = []
    buffer: list[DocumentElement] = []
    buffer_tokens = 0
    # Overlap text carried forward from the previous chunk in this section
    overlap_prefix = ""
    chunk_index_in_section = 0

    def _flush(
        buf: list[DocumentElement],
        buf_tokens: int,
        prefix: str,
        is_atomic: bool = False,
    ) -> None:
        nonlocal chunk_index_in_section
        if not buf:
            return
        text_parts: list[str] = []
        if prefix:
            text_parts.append(prefix)
        text_parts.extend(el.text for el in buf)
        text = "\n\n".join(text_parts)
        types = list({el.type for el in buf})
        token_count = _count_tokens(text)
        chunk = Chunk(
            course_id=course_id,
            chapter=chapter.chapter,
            chapter_title=chapter.title,
            section=section.section,
            section_title=section.title,
            chunk_index=chunk_index_in_section,
            element_types=types,
            text=text,
            token_count=token_count,
        )
        chunks.append(chunk)
        chunk_index_in_section += 1

    for element in section.elements:
        # Skip headings — they are boundaries, not content
        if element.type in HEADING_ELEMENT_TYPES:
            if buffer:
                _flush(buffer, buffer_tokens, overlap_prefix)
                overlap_prefix = _overlap_tokens(
                    "\n\n".join(el.text for el in buffer), _OVERLAP_FRACTION
                )
                buffer = []
                buffer_tokens = 0
            continue

        el_tokens = _count_tokens(element.text)

        if element.type in ATOMIC_ELEMENT_TYPES:
            # Atomic elements: flush current buffer first, then emit as own chunk
            # Exception: if previous paragraph is tiny (<100 tokens), prepend it
            if buffer:
                # Check if we can prepend the last paragraph
                last_is_small = (
                    len(buffer) == 1
                    and buffer[-1].type == "paragraph"
                    and _count_tokens(buffer[-1].text) < 100
                )
                if last_is_small:
                    # Keep the paragraph — it will be included in this atomic chunk
                    prepend = buffer.pop()
                    buffer_tokens -= _count_tokens(prepend.text)
                    if buffer:
                        _flush(buffer, buffer_tokens, overlap_prefix)
                        overlap_prefix = _overlap_tokens(
                            "\n\n".join(el.text for el in buffer), _OVERLAP_FRACTION
                        )
                        buffer = []
                        buffer_tokens = 0
                    # Emit atomic chunk with the prepended paragraph
                    _flush([prepend, element], 0, overlap_prefix, is_atomic=True)
                    overlap_prefix = _overlap_tokens(element.text, _OVERLAP_FRACTION)
                else:
                    # Flush the buffer first
                    _flush(buffer, buffer_tokens, overlap_prefix)
                    overlap_prefix = _overlap_tokens(
                        "\n\n".join(el.text for el in buffer), _OVERLAP_FRACTION
                    )
                    buffer = []
                    buffer_tokens = 0
                    # Emit atomic chunk alone
                    _flush([element], el_tokens, overlap_prefix, is_atomic=True)
                    overlap_prefix = _overlap_tokens(element.text, _OVERLAP_FRACTION)
            else:
                # Buffer was empty — emit atomic chunk directly
                _flush([element], el_tokens, overlap_prefix, is_atomic=True)
                overlap_prefix = _overlap_tokens(element.text, _OVERLAP_FRACTION)
            continue

        # Normal (non-atomic) element: accumulate into buffer
        if buffer_tokens + el_tokens > _TARGET_MAX_TOKENS and buffer:
            # Flush before adding this element
            _flush(buffer, buffer_tokens, overlap_prefix)
            overlap_prefix = _overlap_tokens(
                "\n\n".join(el.text for el in buffer), _OVERLAP_FRACTION
            )
            buffer = []
            buffer_tokens = 0

        buffer.append(element)
        buffer_tokens += el_tokens

    # Flush any remaining buffer at end of section
    if buffer:
        _flush(buffer, buffer_tokens, overlap_prefix)

    return chunks


__all__ = ["chunk_document"]
