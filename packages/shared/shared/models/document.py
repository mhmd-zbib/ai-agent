"""Shared document models for the ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

# ──────────────────────────────────────────────
# Stage 1 — Document Restructuring
# ──────────────────────────────────────────────

ELEMENT_TYPES = frozenset(
    {
        "heading_h1",
        "heading_h2",
        "heading_h3",
        "paragraph",
        "code",
        "table",
        "list",
        "math",
        "figure_caption",
    }
)

ATOMIC_ELEMENT_TYPES = frozenset({"code", "table", "math"})
HEADING_ELEMENT_TYPES = frozenset({"heading_h1", "heading_h2", "heading_h3"})


@dataclass
class DocumentElement:
    type: str  # one of ELEMENT_TYPES
    text: str
    language: str | None = None  # for code blocks only


@dataclass
class Section:
    section: int
    title: str
    elements: list[DocumentElement] = field(default_factory=list)


@dataclass
class Chapter:
    chapter: int
    title: str
    sections: list[Section] = field(default_factory=list)


@dataclass
class ParsedDocument:
    course_id: str
    source_type: str  # textbook | slides | lecture_notes | exercises
    chapters: list[Chapter] = field(default_factory=list)


# ──────────────────────────────────────────────
# Stage 2 — Chunking
# ──────────────────────────────────────────────


@dataclass
class Chunk:
    course_id: str
    chapter: int
    chapter_title: str
    section: int
    section_title: str
    chunk_index: int
    element_types: list[str]
    text: str
    token_count: int
    # Populated in Stage 3
    summary: str | None = None
    keywords: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────
# Stage 3 — Metadata
# ──────────────────────────────────────────────


@dataclass
class ChunkMetadata:
    summary: str
    keywords: list[str]
    questions: list[str]


@dataclass
class SectionSummary:
    course_id: str
    chapter: int
    chapter_title: str
    section: int
    section_title: str
    text: str


@dataclass
class ChapterSummary:
    course_id: str
    chapter: int
    chapter_title: str
    text: str


@dataclass
class CourseSummary:
    course_id: str
    text: str


# ──────────────────────────────────────────────
# API Schemas (Pydantic)
# ──────────────────────────────────────────────


class IngestRequest(BaseModel):
    course_id: str
    source_type: str


class IngestResult(BaseModel):
    course_id: str
    ingested_chunks: int
    summaries_created: int
