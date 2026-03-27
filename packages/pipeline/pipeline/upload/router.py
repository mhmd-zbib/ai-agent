"""HTTP routes for document upload (initiate + complete)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from pipeline.dependencies import get_upload_service
from pipeline.upload.schemas import (
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadInitiateRequest,
    UploadInitiateResponse,
)
from pipeline.upload.service import UploadService

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post(
    "",
    summary="Initiate a multipart upload",
    description=(
        "Registers a new upload and returns presigned PUT URLs — one per chunk. "
        "The client uploads each chunk directly to MinIO using these URLs. "
        "Call POST /v1/uploads/{upload_id}/complete once all chunks have been transferred."
    ),
    response_model=UploadInitiateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_upload(
    body: UploadInitiateRequest,
    service: UploadService = Depends(get_upload_service),
) -> UploadInitiateResponse:
    return service.initiate_upload(request=body, user_id=None)


@router.post(
    "/{upload_id}/complete",
    summary="Complete a multipart upload",
    description=(
        "Confirms that all chunks have been uploaded to MinIO. "
        "The backend writes the manifest, creates a document record (status=uploaded), "
        "and publishes a DocumentUploadedEvent to the pipeline fanout exchange."
    ),
    response_model=UploadCompleteResponse,
    status_code=status.HTTP_200_OK,
)
async def complete_upload(
    upload_id: str,
    body: UploadCompleteRequest,
    service: UploadService = Depends(get_upload_service),
) -> UploadCompleteResponse:
    return service.complete_upload(upload_id=upload_id, request=body, user_id=None)
