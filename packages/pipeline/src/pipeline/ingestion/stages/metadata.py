"""Metadata generation transform — Anthropic enrichment.

Migrated from pipeline.ingestion.stage3_metadata (Stage 3 — Metadata Generation).

Generates summary, keywords, and questions per chunk using the Anthropic API.
Also produces section, chapter, and course-level summaries.

All metadata is generated via a single combined API call per chunk to avoid
redundant round-trips.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import anthropic
from common.models.document import (
    Chapter,
    ChapterSummary,
    Chunk,
    ChunkMetadata,
    CourseSummary,
    ParsedDocument,
    Section,
    SectionSummary,
)

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-5"
_BATCH_SIZE = 20
_BATCH_DELAY_SECONDS = 1.0
_MAX_RETRIES = 5
_BASE_DELAY = 1.0

_COMBINED_SYSTEM_PROMPT = (
    "You generate metadata for course material chunks used in a student AI tutor. "
    "Always return valid JSON matching the exact schema provided."
)

_COMBINED_USER_TEMPLATE = """\
Generate metadata for this course content chunk.

Chapter: {chapter_title}
Section: {section_title}
Content types: {element_types}

Content:
{chunk_text}

Return this exact JSON structure:
{{
  "summary": "1-2 sentence summary of what this chunk explains and what a student learns",
  "keywords": ["3-8 technical terms, function names, concept names"],
  "questions": ["3-5 questions a student would type to find this chunk"]
}}

For questions: write them the way a real student types in chat — informal, sometimes
imprecise, everyday language. Not textbook language.
Return JSON only. No markdown, no explanation."""

_SECTION_SUMMARY_TEMPLATE = """\
Summarize this course section in 1-2 sentences.
Focus on what concept it explains and what a student learns.
Be direct. No filler phrases like "This section discusses..."

Chapter: {chapter_title}
Section: {section_title}

Content:
{section_text}

Return plain text only. No JSON, no markdown."""

_CHAPTER_SUMMARY_TEMPLATE = """\
Write a 3-5 sentence summary of this chapter based on its section summaries.
Do not repeat individual section summaries verbatim — synthesise them.

Chapter: {chapter_title}

Section summaries:
{section_summaries}

Return plain text only. No JSON, no markdown."""

_COURSE_SUMMARY_TEMPLATE = """\
Write a 4-6 sentence summary of this course based on its chapter summaries.
Focus on the overall learning arc and key concepts.

Chapter summaries:
{chapter_summaries}

Return plain text only. No JSON, no markdown."""


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


async def generate_metadata(
    chunks: list[Chunk],
    doc: ParsedDocument,
    api_key: str | None = None,
) -> tuple[list[Chunk], list[SectionSummary], list[ChapterSummary], CourseSummary]:
    """Generate all metadata for *chunks* and the document hierarchy.

    Parameters
    ----------
    chunks:
        Output of Stage 2 — list of Chunk objects (modified in-place with metadata).
    doc:
        The original ParsedDocument — used to generate section/chapter/course summaries.
    api_key:
        Anthropic API key. Falls back to ``ANTHROPIC_API_KEY`` env var.

    Returns
    -------
    tuple of (enriched_chunks, section_summaries, chapter_summaries, course_summary)
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.AsyncAnthropic(api_key=key)

    # Stage 3a: per-chunk metadata
    enriched = await _enrich_chunks(chunks, client)

    # Stage 3b: hierarchical summaries
    (
        section_summaries,
        chapter_summaries,
        course_summary,
    ) = await _generate_hierarchical_summaries(doc, client)

    logger.info(
        "Metadata generation complete",
        extra={
            "course_id": doc.course_id,
            "chunks": len(enriched),
            "section_summaries": len(section_summaries),
            "chapter_summaries": len(chapter_summaries),
        },
    )
    return enriched, section_summaries, chapter_summaries, course_summary


# ──────────────────────────────────────────────────────────────────────────────
# Per-chunk metadata
# ──────────────────────────────────────────────────────────────────────────────


async def _enrich_chunks(
    chunks: list[Chunk], client: anthropic.AsyncAnthropic
) -> list[Chunk]:
    """Add summary, keywords, and questions to every chunk."""
    for batch_start in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[batch_start : batch_start + _BATCH_SIZE]
        tasks = [_enrich_single_chunk(chunk, client) for chunk in batch]
        await asyncio.gather(*tasks)

        if batch_start + _BATCH_SIZE < len(chunks):
            await asyncio.sleep(_BATCH_DELAY_SECONDS)

    return chunks


async def _enrich_single_chunk(chunk: Chunk, client: anthropic.AsyncAnthropic) -> None:
    """Fetch metadata for one chunk and update it in-place."""
    prompt = _COMBINED_USER_TEMPLATE.format(
        chapter_title=chunk.chapter_title,
        section_title=chunk.section_title,
        element_types=", ".join(chunk.element_types),
        chunk_text=chunk.text[:4000],  # guard against very large chunks
    )
    raw = await _call_anthropic_with_retry(client, _COMBINED_SYSTEM_PROMPT, prompt)
    metadata = _parse_chunk_metadata(raw)
    chunk.summary = metadata.summary
    chunk.keywords = metadata.keywords
    chunk.questions = metadata.questions


def _parse_chunk_metadata(raw: str) -> ChunkMetadata:
    """Parse the combined JSON response from the LLM."""
    try:
        # Strip any accidental markdown code fences
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        return ChunkMetadata(
            summary=str(data.get("summary", "")),
            keywords=[str(k) for k in data.get("keywords", [])],
            questions=[str(q) for q in data.get("questions", [])],
        )
    except (json.JSONDecodeError, KeyError) as exc:
        logger.warning(
            "Failed to parse chunk metadata JSON",
            extra={"error": str(exc), "raw": raw[:200]},
        )
        return ChunkMetadata(summary="", keywords=[], questions=[])


# ──────────────────────────────────────────────────────────────────────────────
# Hierarchical summaries
# ──────────────────────────────────────────────────────────────────────────────


async def _generate_hierarchical_summaries(
    doc: ParsedDocument,
    client: anthropic.AsyncAnthropic,
) -> tuple[list[SectionSummary], list[ChapterSummary], CourseSummary]:
    """Generate section -> chapter -> course summaries bottom-up."""
    section_summaries: list[SectionSummary] = []
    chapter_summaries: list[ChapterSummary] = []

    for chapter in doc.chapters:
        ch_section_summaries = await _summarise_sections(chapter, doc.course_id, client)
        section_summaries.extend(ch_section_summaries)

        # Chapter summary is built from section summaries (not raw text)
        ch_summary = await _summarise_chapter(
            chapter, ch_section_summaries, doc.course_id, client
        )
        chapter_summaries.append(ch_summary)

    # Course summary built from chapter summaries (not raw text)
    course_summary = await _summarise_course(doc.course_id, chapter_summaries, client)

    return section_summaries, chapter_summaries, course_summary


async def _summarise_sections(
    chapter: Chapter,
    course_id: str,
    client: anthropic.AsyncAnthropic,
) -> list[SectionSummary]:
    """Generate a summary for every section in a chapter concurrently."""
    tasks = [
        _summarise_one_section(section, chapter, course_id, client)
        for section in chapter.sections
    ]
    return list(await asyncio.gather(*tasks))


async def _summarise_one_section(
    section: Section,
    chapter: Chapter,
    course_id: str,
    client: anthropic.AsyncAnthropic,
) -> SectionSummary:
    """Generate a summary for a single section."""
    section_text = "\n\n".join(el.text for el in section.elements)[:6000]
    prompt = _SECTION_SUMMARY_TEMPLATE.format(
        chapter_title=chapter.title,
        section_title=section.title,
        section_text=section_text,
    )
    text = await _call_anthropic_with_retry(client, "", prompt)
    return SectionSummary(
        course_id=course_id,
        chapter=chapter.chapter,
        chapter_title=chapter.title,
        section=section.section,
        section_title=section.title,
        text=text.strip(),
    )


async def _summarise_chapter(
    chapter: Chapter,
    section_summaries: list[SectionSummary],
    course_id: str,
    client: anthropic.AsyncAnthropic,
) -> ChapterSummary:
    """Generate a summary for a chapter from its section summaries."""
    combined = "\n\n".join(
        f"Section {s.section} — {s.section_title}:\n{s.text}" for s in section_summaries
    )
    prompt = _CHAPTER_SUMMARY_TEMPLATE.format(
        chapter_title=chapter.title,
        section_summaries=combined[:8000],
    )
    text = await _call_anthropic_with_retry(client, "", prompt)
    return ChapterSummary(
        course_id=course_id,
        chapter=chapter.chapter,
        chapter_title=chapter.title,
        text=text.strip(),
    )


async def _summarise_course(
    course_id: str,
    chapter_summaries: list[ChapterSummary],
    client: anthropic.AsyncAnthropic,
) -> CourseSummary:
    """Generate a course-level summary from all chapter summaries."""
    combined = "\n\n".join(
        f"Chapter {c.chapter} — {c.chapter_title}:\n{c.text}" for c in chapter_summaries
    )
    prompt = _COURSE_SUMMARY_TEMPLATE.format(chapter_summaries=combined[:10000])
    text = await _call_anthropic_with_retry(client, "", prompt)
    return CourseSummary(course_id=course_id, text=text.strip())


# ──────────────────────────────────────────────────────────────────────────────
# API call with exponential backoff
# ──────────────────────────────────────────────────────────────────────────────


async def _call_anthropic_with_retry(
    client: anthropic.AsyncAnthropic,
    system: str,
    user: str,
) -> str:
    """Call the Anthropic API with exponential backoff on rate-limit errors."""
    delay = _BASE_DELAY
    messages: list[anthropic.types.MessageParam] = [{"role": "user", "content": user}]

    for attempt in range(_MAX_RETRIES):
        try:
            if system:
                response = await client.messages.create(
                    model=_MODEL,
                    max_tokens=1024,
                    system=system,
                    messages=messages,
                )
            else:
                response = await client.messages.create(
                    model=_MODEL,
                    max_tokens=1024,
                    messages=messages,
                )
            content = response.content[0]
            if hasattr(content, "text"):
                return str(content.text)
            return ""
        except anthropic.RateLimitError:
            if attempt == _MAX_RETRIES - 1:
                raise
            wait = delay * (2**attempt)
            logger.warning(
                "Anthropic rate limit hit, retrying",
                extra={"attempt": attempt + 1, "wait_seconds": wait},
            )
            await asyncio.sleep(wait)
        except anthropic.APIStatusError as exc:
            logger.error(
                "Anthropic API error",
                extra={"status": exc.status_code, "error": str(exc)},
            )
            raise

    return ""  # unreachable


__all__ = ["generate_metadata"]
