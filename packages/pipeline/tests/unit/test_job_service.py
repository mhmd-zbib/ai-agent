"""Unit tests for JobService and JobRepository."""

from __future__ import annotations

import pytest

from shared.models.job import JobStatus

from pipeline.jobs.repository import JobRepository
from pipeline.jobs.service import JobService


# ---------------------------------------------------------------------------
# JobRepository
# ---------------------------------------------------------------------------


class TestJobRepository:
    def test_save_and_get(self) -> None:
        repo = JobRepository()
        from shared.models.job import PipelineJob

        job = PipelineJob(job_id="j1", status=JobStatus.PENDING, document_path="doc/path")
        repo.save(job)
        retrieved = repo.get("j1")
        assert retrieved is not None
        assert retrieved.job_id == "j1"
        assert retrieved.status == JobStatus.PENDING

    def test_get_returns_none_for_unknown_id(self) -> None:
        repo = JobRepository()
        assert repo.get("does-not-exist") is None

    def test_update_status_transitions_state(self) -> None:
        repo = JobRepository()
        from shared.models.job import PipelineJob

        job = PipelineJob(job_id="j2", status=JobStatus.PENDING, document_path="x")
        repo.save(job)

        updated = repo.update_status("j2", JobStatus.PROCESSING)
        assert updated is not None
        assert updated.status == JobStatus.PROCESSING

    def test_update_status_sets_completed_at_on_terminal(self) -> None:
        repo = JobRepository()
        from shared.models.job import PipelineJob

        job = PipelineJob(job_id="j3", status=JobStatus.PENDING, document_path="x")
        repo.save(job)
        repo.update_status("j3", JobStatus.PROCESSING)
        updated = repo.update_status("j3", JobStatus.COMPLETED)
        assert updated is not None
        assert updated.completed_at is not None

    def test_update_status_sets_error_on_failed(self) -> None:
        repo = JobRepository()
        from shared.models.job import PipelineJob

        job = PipelineJob(job_id="j4", status=JobStatus.PENDING, document_path="x")
        repo.save(job)
        updated = repo.update_status("j4", JobStatus.FAILED, error="timeout")
        assert updated is not None
        assert updated.error == "timeout"

    def test_update_status_returns_none_for_unknown(self) -> None:
        repo = JobRepository()
        assert repo.update_status("ghost", JobStatus.COMPLETED) is None

    def test_list_all_empty(self) -> None:
        repo = JobRepository()
        jobs, total = repo.list_all()
        assert jobs == []
        assert total == 0

    def test_list_all_pagination(self) -> None:
        repo = JobRepository()
        from shared.models.job import PipelineJob

        for i in range(5):
            repo.save(PipelineJob(job_id=f"j{i}", status=JobStatus.PENDING, document_path="x"))

        page1, total = repo.list_all(page=1, page_size=3)
        page2, _ = repo.list_all(page=2, page_size=3)

        assert total == 5
        assert len(page1) == 3
        assert len(page2) == 2

    def test_delete_existing_job(self) -> None:
        repo = JobRepository()
        from shared.models.job import PipelineJob

        job = PipelineJob(job_id="del-me", status=JobStatus.PENDING, document_path="x")
        repo.save(job)
        assert repo.delete("del-me") is True
        assert repo.get("del-me") is None

    def test_delete_nonexistent_returns_false(self) -> None:
        repo = JobRepository()
        assert repo.delete("nope") is False


# ---------------------------------------------------------------------------
# JobService
# ---------------------------------------------------------------------------


class TestJobService:
    def test_create_job_returns_pending_status(self, job_service: JobService) -> None:
        response = job_service.create_job("documents/test.pdf")
        assert response.status == JobStatus.PENDING
        assert response.document_path == "documents/test.pdf"
        assert response.job_id

    def test_create_job_persists_to_repository(
        self, job_service: JobService, job_repository: JobRepository
    ) -> None:
        response = job_service.create_job("documents/test.pdf")
        stored = job_repository.get(response.job_id)
        assert stored is not None

    def test_get_job_returns_existing(self, job_service: JobService) -> None:
        created = job_service.create_job("doc.pdf")
        retrieved = job_service.get_job(created.job_id)
        assert retrieved is not None
        assert retrieved.job_id == created.job_id

    def test_get_job_returns_none_for_unknown(self, job_service: JobService) -> None:
        assert job_service.get_job("nonexistent") is None

    def test_mark_processing_transitions_status(self, job_service: JobService) -> None:
        created = job_service.create_job("doc.pdf")
        updated = job_service.mark_processing(created.job_id)
        assert updated is not None
        assert updated.status == JobStatus.PROCESSING

    def test_mark_completed_transitions_status(self, job_service: JobService) -> None:
        created = job_service.create_job("doc.pdf")
        job_service.mark_processing(created.job_id)
        updated = job_service.mark_completed(created.job_id)
        assert updated is not None
        assert updated.status == JobStatus.COMPLETED
        assert updated.completed_at is not None

    def test_mark_failed_sets_error(self, job_service: JobService) -> None:
        created = job_service.create_job("doc.pdf")
        updated = job_service.mark_failed(created.job_id, "parse error")
        assert updated is not None
        assert updated.status == JobStatus.FAILED
        assert updated.error == "parse error"

    def test_mark_processing_returns_none_for_unknown(self, job_service: JobService) -> None:
        assert job_service.mark_processing("ghost") is None

    def test_list_jobs_empty(self, job_service: JobService) -> None:
        result = job_service.list_jobs()
        assert result.total == 0
        assert result.items == []

    def test_list_jobs_pagination(self, job_service: JobService) -> None:
        for i in range(5):
            job_service.create_job(f"doc{i}.pdf")

        page1 = job_service.list_jobs(page=1, page_size=3)
        page2 = job_service.list_jobs(page=2, page_size=3)

        assert page1.total == 5
        assert len(page1.items) == 3
        assert len(page2.items) == 2

    def test_list_jobs_caps_page_size_at_max(self, job_service: JobService) -> None:
        result = job_service.list_jobs(page=1, page_size=9999)
        assert result.page_size == 100  # capped at _MAX_PAGE_SIZE
