"""Job tracking service — creates, reads, and updates PipelineJob records."""

from __future__ import annotations

from uuid import uuid4

from shared.logging import get_logger
from shared.models.job import JobStatus, PipelineJob

from pipeline.jobs.repository import JobRepository
from pipeline.jobs.schemas import JobListResponse, JobResponse

logger = get_logger(__name__)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100


class JobService:
    """Business logic for pipeline job lifecycle management."""

    def __init__(self, repository: JobRepository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create_job(self, document_path: str) -> JobResponse:
        """Create a new job in PENDING status and persist it.

        Args:
            document_path: Storage path or object key of the document.

        Returns:
            The serialized job record.
        """
        job = PipelineJob(
            job_id=str(uuid4()),
            status=JobStatus.PENDING,
            document_path=document_path,
        )
        self._repo.save(job)
        logger.info(
            "Pipeline job created",
            extra={"job_id": job.job_id, "document_path": document_path},
        )
        return _to_response(job)

    def mark_processing(self, job_id: str) -> JobResponse | None:
        """Transition job to PROCESSING.  Returns ``None`` when not found."""
        job = self._repo.update_status(job_id, JobStatus.PROCESSING)
        if job is None:
            logger.warning("Job not found for mark_processing", extra={"job_id": job_id})
            return None
        logger.info("Job is now processing", extra={"job_id": job_id})
        return _to_response(job)

    def mark_completed(self, job_id: str) -> JobResponse | None:
        """Transition job to COMPLETED.  Returns ``None`` when not found."""
        job = self._repo.update_status(job_id, JobStatus.COMPLETED)
        if job is None:
            logger.warning("Job not found for mark_completed", extra={"job_id": job_id})
            return None
        logger.info("Job completed successfully", extra={"job_id": job_id})
        return _to_response(job)

    def mark_failed(self, job_id: str, error: str) -> JobResponse | None:
        """Transition job to FAILED with an error message.  Returns ``None`` when not found."""
        job = self._repo.update_status(job_id, JobStatus.FAILED, error=error)
        if job is None:
            logger.warning("Job not found for mark_failed", extra={"job_id": job_id})
            return None
        logger.warning("Job failed", extra={"job_id": job_id, "error": error})
        return _to_response(job)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_job(self, job_id: str) -> JobResponse | None:
        """Return the job with *job_id*, or ``None`` when not found."""
        job = self._repo.get(job_id)
        if job is None:
            return None
        return _to_response(job)

    def list_jobs(self, *, page: int = 1, page_size: int = _DEFAULT_PAGE_SIZE) -> JobListResponse:
        """Return a paginated list of all jobs (newest first).

        Args:
            page:      1-based page number.
            page_size: Items per page (capped at ``_MAX_PAGE_SIZE``).
        """
        page = max(1, page)
        page_size = min(max(1, page_size), _MAX_PAGE_SIZE)
        jobs, total = self._repo.list_all(page=page, page_size=page_size)
        return JobListResponse(
            items=[_to_response(j) for j in jobs],
            total=total,
            page=page,
            page_size=page_size,
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _to_response(job: PipelineJob) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        status=job.status,
        document_path=job.document_path,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error=job.error,
    )
