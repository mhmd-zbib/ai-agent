from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.modules.documents.schemas import DocumentUploadResponse
from app.modules.documents.services import DocumentService
from app.modules.users.schemas import UserOut
from app.shared import deps

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.post("/uploads", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    chunk_size_bytes: int | None = Form(default=None, ge=1024, le=10 * 1024 * 1024),
    current_user: UserOut = Depends(deps.get_current_user),
    document_service: DocumentService = Depends(deps.get_document_service),
) -> DocumentUploadResponse:
    return document_service.upload_chunked_document(
        file=file,
        user_id=current_user.id,
        chunk_size_bytes=chunk_size_bytes,
    )
