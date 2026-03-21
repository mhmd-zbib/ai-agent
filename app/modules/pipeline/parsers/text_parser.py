import re

from app.modules.pipeline.parsers.base import BaseParser, ParsedDocument, clean_text


class TextParser(BaseParser):
    """
    Parser for plain text and Markdown files.

    Detects section breaks on blank lines, ATX headings (``# …``), and
    setext-style headings (underlines of ``=`` or ``-``).
    """

    _SETEXT_RE = re.compile(r"^[=-]{2,}\s*$")

    def parse(self, content: bytes, file_name: str = "") -> ParsedDocument:
        raw = content.decode("utf-8", errors="replace")
        text = clean_text(raw)
        return ParsedDocument(text=text, pages=None)
