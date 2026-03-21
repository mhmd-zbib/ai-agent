from io import BytesIO

from app.modules.pipeline.parsers.base import BaseParser, ParsedDocument, clean_text


class PdfParser(BaseParser):
    """
    Extracts text from PDFs using pypdf.

    Each page's text is preserved separately (``ParsedDocument.pages``).
    The ``text`` field is the full concatenation, cleaned and ready for chunking.
    """

    def parse(self, content: bytes, file_name: str = "") -> ParsedDocument:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        pages: list[str] = []

        for page in reader.pages:
            raw = page.extract_text() or ""
            cleaned = clean_text(raw)
            if cleaned:
                pages.append(cleaned)

        full_text = "\n\n".join(pages)
        return ParsedDocument(text=full_text, pages=pages)
