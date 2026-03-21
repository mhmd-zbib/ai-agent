import tiktoken

from app.modules.pipeline.chunkers.base import BaseChunker, Chunk


class SlidingWindowChunker(BaseChunker):
    """
    Token-based sliding window chunker.

    Uses tiktoken to tokenize the full document text, then emits windows of
    *window_tokens* tokens with *overlap_tokens* of shared context between
    consecutive chunks.  Each window is decoded back to a UTF-8 string so
    downstream consumers receive plain text, not token IDs.

    The default encoding ``cl100k_base`` is used by text-embedding-3-small,
    text-embedding-ada-002, gpt-4, and gpt-3.5-turbo, so token counts align
    exactly with what the embedding model sees.

    For PDFs (when *pages* is provided) the source page of each chunk is
    determined by mapping token positions back to the originating page.

    Args:
        window_tokens: Target chunk size in tokens (default 512).
        overlap_tokens: Tokens shared between consecutive chunks (default 50).
        encoding:       tiktoken encoding name (default ``cl100k_base``).
    """

    def __init__(
        self,
        *,
        window_tokens: int = 512,
        overlap_tokens: int = 50,
        encoding: str = "cl100k_base",
    ) -> None:
        if overlap_tokens >= window_tokens:
            raise ValueError("overlap_tokens must be less than window_tokens")
        self._window = window_tokens
        self._overlap = overlap_tokens
        self._enc = tiktoken.get_encoding(encoding)

    def chunk(
        self,
        *,
        document_id: str,
        text: str,
        pages: list[str] | None = None,
    ) -> list[Chunk]:
        tokens = self._enc.encode(text)
        if not tokens:
            return []

        page_map: dict[int, int] = {}
        if pages:
            page_map = _build_page_map(self._enc, tokens, pages)

        stride = max(1, self._window - self._overlap)
        chunks: list[Chunk] = []
        chunk_index = 0
        start = 0

        while start < len(tokens):
            end = min(start + self._window, len(tokens))
            chunk_text = self._enc.decode(tokens[start:end])

            chunks.append(
                Chunk(
                    chunk_id=f"{document_id}_chunk_{chunk_index:06d}",
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    source_page=page_map.get(start) if page_map else None,
                )
            )

            chunk_index += 1
            start += stride

        return chunks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_page_map(
    enc: tiktoken.Encoding,
    all_tokens: list[int],
    pages: list[str],
) -> dict[int, int]:
    """Map each token index to its 1-based page number."""
    page_map: dict[int, int] = {}
    token_idx = 0
    for page_number, page_text in enumerate(pages, start=1):
        page_token_count = len(enc.encode(page_text))
        for _ in range(page_token_count):
            if token_idx < len(all_tokens):
                page_map[token_idx] = page_number
                token_idx += 1
    return page_map
