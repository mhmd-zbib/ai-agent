"""E2E tests for the /v1/jobs endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pipeline.jobs.service import JobService


def test_list_jobs_empty(app_client: TestClient) -> None:
    response = app_client.get("/v1/jobs")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_list_jobs_with_data(app_client: TestClient, job_service: JobService) -> None:
    job_service.create_job("documents/doc1.pdf")
    job_service.create_job("documents/doc2.pdf")

    response = app_client.get("/v1/jobs")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_get_job_by_id_found(app_client: TestClient, job_service: JobService) -> None:
    created = job_service.create_job("documents/test.pdf")

    response = app_client.get(f"/v1/jobs/{created.job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == created.job_id
    assert body["status"] == "pending"


def test_get_job_by_id_not_found(app_client: TestClient) -> None:
    response = app_client.get("/v1/jobs/does-not-exist")
    assert response.status_code == 404


def test_list_jobs_pagination(app_client: TestClient, job_service: JobService) -> None:
    for i in range(5):
        job_service.create_job(f"doc{i}.pdf")

    response = app_client.get("/v1/jobs?page=1&page_size=2")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2
