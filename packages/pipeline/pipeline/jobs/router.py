"""HTTP routes for pipeline job status and listing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from pipeline.dependencies import get_job_service
from pipeline.jobs.schemas import JobListResponse, JobResponse
from pipeline.jobs.service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "",
    summary="List pipeline jobs",
    description=(
        "Returns a paginated list of all pipeline jobs, ordered by creation time "
        "(newest first). Use the ``page`` and ``page_size`` query parameters to "
        "navigate through results. Maximum page size is 100."
    ),
    response_model=JobListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_jobs(
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    service: JobService = Depends(get_job_service),
) -> JobListResponse:
    return service.list_jobs(page=page, page_size=page_size)


@router.get(
    "/{job_id}",
    summary="Get a pipeline job by ID",
    description=(
        "Returns the current status of a single pipeline job. "
        "Poll this endpoint to track progress from PENDING through PROCESSING "
        "to either COMPLETED or FAILED."
    ),
    response_model=JobResponse,
    status_code=status.HTTP_200_OK,
)
async def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> JobResponse:
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )
    return job
