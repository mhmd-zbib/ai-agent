"""FastAPI dependency providers for the pipeline application.

All providers read from ``app.state`` which is populated during lifespan
startup in ``pipeline.main``.  Route handlers use ``Depends(get_*)`` — they
never instantiate services or infrastructure directly.
"""

from __future__ import annotations

from fastapi import Request

from pipeline.jobs.repository import JobRepository
from pipeline.jobs.service import JobService
from pipeline.upload.service import UploadService


def get_upload_service(request: Request) -> UploadService:
    """Return the singleton UploadService wired in lifespan."""
    return request.app.state.upload_service  # type: ignore[no-any-return]


def get_job_repository(request: Request) -> JobRepository:
    """Return the singleton JobRepository wired in lifespan."""
    return request.app.state.job_repository  # type: ignore[no-any-return]


def get_job_service(request: Request) -> JobService:
    """Return the singleton JobService wired in lifespan."""
    return request.app.state.job_service  # type: ignore[no-any-return]
