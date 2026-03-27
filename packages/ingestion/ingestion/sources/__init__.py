"""Document source adapters — read raw files into ParsedDocument."""

from ingestion.sources.base import BaseSource
from ingestion.sources.pdf import DocxSource, PdfSource

__all__ = ["BaseSource", "PdfSource", "DocxSource"]
