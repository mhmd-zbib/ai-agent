"""app.documents.router — Upload endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth.schemas import UserOut
from api.dependencies import get_current_user, get_document_upload_service
from api.documents.schemas import (
    BucketInfoRequest,
    BucketInfoResponse,
    ChunkUploadNotification,
    ChunkUploadResponse,
    DocumentUploadCompleteRequest,
    DocumentUploadCompleteResponse,
)
from api.documents.service import DocumentUploadService
from common.core.log_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.post("/initiate-upload", response_model=BucketInfoResponse)
async def initiate_upload(
    request: BucketInfoRequest,
    upload_service: DocumentUploadService = Depends(get_document_upload_service),
    user: UserOut = Depends(get_current_user),
) -> BucketInfoResponse:
    """
    **Step 1: Client initiates document upload**

    Returns bucket credentials and chunking metadata.

    Request body:
    ```json
    {
        "document_name": "lecture_notes.pdf",
        "content_type": "application/pdf",
        "total_size_bytes": 104857600,
        "chunking_strategy": "fixed"
    }
    ```

    Response includes:
    - `upload_session_id`: Use in subsequent API calls
    - `presigned_url`: Direct upload URL to MinIO bucket
    - `chunk_size_bytes`: Recommended chunk size (5MB)
    - `max_chunks`: Maximum chunks for this upload
    """
    try:
        response = upload_service.initiate_upload(request, user.id)
        return response
    except Exception as e:
        logger.error(
            "Failed to initiate upload",
            extra={"user_id": user.id, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate upload: {str(e)}",
        ) from e


@router.post("/chunk-received", response_model=ChunkUploadResponse)
async def notify_chunk_received(
    notification: ChunkUploadNotification,
    upload_service: DocumentUploadService = Depends(get_document_upload_service),
    user: UserOut = Depends(get_current_user),
) -> ChunkUploadResponse:
    """
    **Step 2: Client notifies backend of chunk completion**

    Called after each chunk is uploaded to the bucket.

    Request body:
    ```json
    {
        "upload_session_id": "550e8400-e29b-41d4-a716-446655440000",
        "chunk_number": 1,
        "chunk_hash": "abc123def456...",
        "chunk_size_bytes": 5242880
    }
    ```

    Backend records chunk metadata for later validation.
    """
    try:
        response = upload_service.notify_chunk_received(notification)
        logger.debug(
            "Chunk notification response",
            extra={
                "user_id": user.id,
                "session_id": notification.upload_session_id,
                "chunk": notification.chunk_number,
                "status": response.status,
            },
        )
        return response
    except Exception as e:
        logger.error(
            "Failed to process chunk notification",
            extra={
                "user_id": user.id,
                "session_id": notification.upload_session_id,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process chunk: {str(e)}",
        ) from e


@router.post("/complete-upload", response_model=DocumentUploadCompleteResponse)
async def complete_upload(
    request: DocumentUploadCompleteRequest,
    upload_service: DocumentUploadService = Depends(get_document_upload_service),
    user: UserOut = Depends(get_current_user),
) -> DocumentUploadCompleteResponse:
    """
    **Step 3: Client completes upload and triggers ingestion**

    Call after all chunks have been uploaded and notified.

    Request body:
    ```json
    {
        "upload_session_id": "550e8400-e29b-41d4-a716-446655440000",
        "total_chunks": 5,
        "file_hash": "sha256:...",
        "course_id": "course123",
        "document_metadata": {"subject": "Math", "level": "101"}
    }
    ```

    Backend:
    1. Validates all chunks were received
    2. Publishes DocumentUploadedEvent to RabbitMQ
    3. Pipeline consumer picks up event and starts ingestion
    """
    try:
        response = upload_service.complete_upload(request)
        logger.info(
            "Upload completed successfully",
            extra={
                "user_id": user.id,
                "session_id": request.upload_session_id,
                "job_id": response.ingestion_job_id,
            },
        )
        return response
    except ValueError as e:
        logger.warning(
            "Upload validation failed",
            extra={
                "user_id": user.id,
                "session_id": request.upload_session_id,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            "Failed to complete upload",
            extra={
                "user_id": user.id,
                "session_id": request.upload_session_id,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete upload: {str(e)}",
        ) from e

