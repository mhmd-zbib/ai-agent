"""Text cleaning transform.

Provides lightweight text normalization utilities applied before or after
chunking to ensure consistent, clean input to the embedding model.
"""

from __future__ import annotations

import re
import unicodedata


def clean_text(text: str) -> str:
    """Remove extra whitespace and normalize unicode.

    Steps applied in order:
    1. NFKC unicode normalization (collapses compatibility characters).
    2. Collapse runs of whitespace (spaces, tabs, newlines) into a single space.
    3. Strip leading and trailing whitespace.

    Parameters
    ----------
    text:
        Raw text string to clean.

    Returns
    -------
    str
        Cleaned, normalized text.
    """
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


__all__ = ["clean_text"]
