from fastapi import APIRouter, Depends, status

from app.modules.documents.schemas import UploadCompleteRequest, UploadCompleteResponse, UploadInitiateRequest, UploadInitiateResponse
from app.modules.documents.services import DocumentService
from app.modules.users.schemas import UserOut
from app.shared import deps

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.post("/uploads", response_model=UploadInitiateResponse, status_code=status.HTTP_201_CREATED)
async def initiate_upload(
    body: UploadInitiateRequest,
    current_user: UserOut = Depends(deps.get_current_user),
    document_service: DocumentService = Depends(deps.get_document_service),
) -> UploadInitiateResponse:
    """
    Initiate a chunked upload. Returns presigned PUT URLs — one per chunk.
    The client uploads each chunk directly to MinIO using these URLs.
    Call POST /uploads/{upload_id}/complete when all chunks are uploaded.
    """
    return document_service.initiate_upload(
        request=body,
        user_id=current_user.id,
    )


@router.post("/uploads/{upload_id}/complete", response_model=UploadCompleteResponse, status_code=status.HTTP_200_OK)
async def complete_upload(
    upload_id: str,
    body: UploadCompleteRequest,
    current_user: UserOut = Depends(deps.get_current_user),
    document_service: DocumentService = Depends(deps.get_document_service),
) -> UploadCompleteResponse:
    """
    Confirm all chunks have been uploaded to MinIO.
    Backend writes the manifest and triggers async processing via RabbitMQ.
    """
    return document_service.complete_upload(
        upload_id=upload_id,
        request=body,
        user_id=current_user.id,
    )
