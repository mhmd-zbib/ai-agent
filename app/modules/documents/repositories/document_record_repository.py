from typing import Protocol


class IDocumentRecordRepository(Protocol):
    """Port: create a persistent document record in the backing store."""

    def create_document(
        self,
        *,
        document_id: str,
        upload_id: str,
        user_id: str | None,
        file_name: str,
        content_type: str,
        bucket: str,
        object_prefix: str,
        manifest_key: str,
        upload_chunk_count: int,
        total_size_bytes: int,
    ) -> None: ...
