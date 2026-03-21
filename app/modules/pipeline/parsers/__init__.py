from app.modules.pipeline.parsers.base import BaseParser, ParsedDocument
from app.modules.pipeline.parsers.docx_parser import DocxParser
from app.modules.pipeline.parsers.pdf_parser import PdfParser
from app.modules.pipeline.parsers.text_parser import TextParser

__all__ = [
    "BaseParser",
    "DocxParser",
    "ParsedDocument",
    "PdfParser",
    "TextParser",
]


def get_parser(content_type: str | None, file_name: str = "") -> BaseParser:
    """Return the appropriate parser for the given content type / file extension."""
    ct = (content_type or "").lower()
    name = file_name.lower()

    if ct == "application/pdf" or name.endswith(".pdf"):
        return PdfParser()

    if ct in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ) or name.endswith((".docx", ".doc")):
        return DocxParser()

    return TextParser()
