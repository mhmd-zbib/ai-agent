"""CLI entrypoint for the ingestion pipeline.

Usage:
    python -m pipeline.cli ingest --course-id CS101 --file ./book.pdf --source-type textbook
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from ingestion.orchestrator import ingest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_VALID_SOURCE_TYPES = ("textbook", "slides", "lecture_notes", "exercises")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline.cli",
        description="Ingest a course document into the AI tutor database.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_p = sub.add_parser("ingest", help="Ingest a document file.")
    ingest_p.add_argument(
        "--course-id", required=True, help="Course identifier (e.g. CS101)."
    )
    ingest_p.add_argument(
        "--file", required=True, help="Path to PDF, EPUB, or DOCX file."
    )
    ingest_p.add_argument(
        "--source-type",
        default="textbook",
        choices=_VALID_SOURCE_TYPES,
        help="Document category (default: textbook).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "ingest":
        result = asyncio.run(
            ingest(
                file_path=args.file,
                course_id=args.course_id,
                source_type=args.source_type,
            )
        )
        print(  # noqa: T201
            f"Ingestion complete: {result.ingested_chunks} chunks, "
            f"{result.summaries_created} summaries"
        )
        print(f"Course ID: {result.course_id}")  # noqa: T201


if __name__ == "__main__":
    main()
