"""Repository for PipelineJob persistence.

The production adapter uses an in-process dict store protected by a threading
lock.  In a real deployment this would be backed by Postgres, but the in-memory
implementation is sufficient for the monorepo phase-4 baseline and simplifies
testing (no DB required).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from shared.models.job import JobStatus, PipelineJob


class JobRepository:
    """Thread-safe in-memory store for PipelineJob records.

    All mutating operations acquire a lock so the repository is safe to use
    from concurrent request handlers.
    """

    def __init__(self) -> None:
        self._store: dict[str, PipelineJob] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save(self, job: PipelineJob) -> None:
        """Insert or replace *job* in the store."""
        with self._lock:
            self._store[job.job_id] = job

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
    ) -> PipelineJob | None:
        """Transition *job_id* to *status*.

        Returns the updated job, or ``None`` when *job_id* is not found.
        Automatically records ``completed_at`` when moving to a terminal state.
        """
        terminal = {JobStatus.COMPLETED, JobStatus.FAILED}
        with self._lock:
            job = self._store.get(job_id)
            if job is None:
                return None
            job.status = status
            job.error = error
            if status in terminal and job.completed_at is None:
                job.completed_at = datetime.now(UTC)
            return job

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, job_id: str) -> PipelineJob | None:
        """Return the job with *job_id*, or ``None``."""
        with self._lock:
            return self._store.get(job_id)

    def list_all(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PipelineJob], int]:
        """Return a page of jobs sorted by creation time (newest first).

        Returns a ``(items, total)`` tuple where *total* is the full count
        before pagination.
        """
        with self._lock:
            all_jobs = sorted(
                self._store.values(),
                key=lambda j: j.created_at,
                reverse=True,
            )
        total = len(all_jobs)
        start = (page - 1) * page_size
        end = start + page_size
        return all_jobs[start:end], total

    def delete(self, job_id: str) -> bool:
        """Remove *job_id* from the store.  Returns ``True`` when found."""
        with self._lock:
            return self._store.pop(job_id, None) is not None
