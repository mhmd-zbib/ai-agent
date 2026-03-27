"""Shared pytest fixtures for the pipeline package tests.

Fixtures are organized in three tiers:
  - Unit:        pure in-memory objects, no I/O.
  - Integration: wires real service objects with mocked infrastructure.
  - E2E:         spins up the full FastAPI app via httpx AsyncClient.

Infrastructure (MinIO, RabbitMQ, Postgres) is always mocked so these tests
require no running containers.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from pipeline.jobs.repository import JobRepository
from pipeline.jobs.service import JobService
from pipeline.upload.repository import IDocumentStorageRepository, IDocumentRecordRepository
from pipeline.upload.service import UploadService


# ---------------------------------------------------------------------------
# In-memory / mock infrastructure doubles
# ---------------------------------------------------------------------------


class FakeStorageRepository:
    """Fake IDocumentStorageRepository — records calls and returns predictable URLs."""

    def __init__(self) -> None:
        self.uploaded: list[dict[str, Any]] = []
        self.presigned_calls: list[dict[str, Any]] = []

    def upload_bytes(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str | None = None,
    ) -> None:
        self.uploaded.append(
            {"object_key": object_key, "payload": payload, "content_type": content_type}
        )

    def presigned_put_url(self, *, object_key: str, expires: timedelta) -> str:
        self.presigned_calls.append({"object_key": object_key, "expires": expires})
        return f"https://minio.example.com/{object_key}?presigned=1"


class FakeRecordRepository:
    """Fake IDocumentRecordRepository — records create_document calls."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create_document(self, **kwargs: Any) -> None:
        self.created.append(kwargs)


class FakePublisher:
    """Fake RabbitMQPublisher — captures published payloads."""

    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    def publish_json(self, payload: dict[str, Any]) -> None:
        self.published.append(payload)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Unit-level fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_storage() -> FakeStorageRepository:
    return FakeStorageRepository()


@pytest.fixture()
def fake_record_repo() -> FakeRecordRepository:
    return FakeRecordRepository()


@pytest.fixture()
def fake_publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture()
def job_repository() -> JobRepository:
    return JobRepository()


@pytest.fixture()
def job_service(job_repository: JobRepository) -> JobService:
    return JobService(job_repository)


@pytest.fixture()
def upload_service(
    fake_storage: FakeStorageRepository,
    fake_publisher: FakePublisher,
    fake_record_repo: FakeRecordRepository,
) -> UploadService:
    return UploadService(
        bucket_name="test-bucket",
        default_chunk_size_bytes=5 * 1024 * 1024,
        storage=fake_storage,  # type: ignore[arg-type]
        publisher=fake_publisher,  # type: ignore[arg-type]
        document_record_repository=fake_record_repo,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# E2E fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_client(
    upload_service: UploadService,
    job_service: JobService,
    job_repository: JobRepository,
) -> TestClient:
    """Return a synchronous TestClient with pre-wired app.state.

    A no-op lifespan is used so the real lifespan never executes during tests
    (which would attempt to connect to MinIO and RabbitMQ).
    """
    from contextlib import asynccontextmanager
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

    from shared.exceptions import register_exception_handlers

    from pipeline.health.router import router as health_router
    from pipeline.jobs.router import router as jobs_router
    from pipeline.upload.router import router as upload_router

    @asynccontextmanager
    async def _noop_lifespan(app: FastAPI) -> AsyncIterator[None]:  # type: ignore[misc]
        yield

    application = FastAPI(title="Pipeline API (test)", lifespan=_noop_lifespan)
    application.include_router(upload_router, prefix="/v1")
    application.include_router(jobs_router, prefix="/v1")
    application.include_router(health_router)
    register_exception_handlers(application)

    # Inject pre-built service instances directly onto app.state
    application.state.upload_service = upload_service
    application.state.job_service = job_service
    application.state.job_repository = job_repository

    with TestClient(application, raise_server_exceptions=True) as client:
        yield client
