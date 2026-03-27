"""E2E tests for the /v1/uploads endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


_INITIATE_PAYLOAD = {
    "file_name": "lecture1.pdf",
    "content_type": "application/pdf",
    "file_size_bytes": 10 * 1024 * 1024,
}


def test_initiate_upload_returns_201(app_client: TestClient) -> None:
    response = app_client.post("/v1/uploads", json=_INITIATE_PAYLOAD)
    assert response.status_code == 201


def test_initiate_upload_response_shape(app_client: TestClient) -> None:
    response = app_client.post("/v1/uploads", json=_INITIATE_PAYLOAD)
    body = response.json()
    assert "upload_id" in body
    assert "chunks" in body
    assert "chunk_count" in body
    assert body["chunk_count"] == len(body["chunks"])
    assert body["bucket"] == "test-bucket"


def test_initiate_upload_each_chunk_has_presigned_url(app_client: TestClient) -> None:
    response = app_client.post("/v1/uploads", json=_INITIATE_PAYLOAD)
    body = response.json()
    for chunk in body["chunks"]:
        assert chunk["presigned_url"].startswith("https://")


def test_initiate_upload_rejects_missing_file_name(app_client: TestClient) -> None:
    response = app_client.post(
        "/v1/uploads",
        json={"file_size_bytes": 1024},
    )
    assert response.status_code == 422


def test_initiate_upload_rejects_zero_file_size(app_client: TestClient) -> None:
    response = app_client.post(
        "/v1/uploads",
        json={"file_name": "doc.pdf", "file_size_bytes": 0},
    )
    assert response.status_code == 422


def test_complete_upload_returns_200(app_client: TestClient) -> None:
    # First initiate
    init_resp = app_client.post("/v1/uploads", json=_INITIATE_PAYLOAD)
    upload_id = init_resp.json()["upload_id"]
    chunk_count = init_resp.json()["chunk_count"]

    complete_payload = {
        "file_name": "lecture1.pdf",
        "content_type": "application/pdf",
        "chunks": [{"chunk_index": i, "size_bytes": 1024} for i in range(chunk_count)],
        "course_code": "CS101",
        "university_name": "LIU",
    }
    response = app_client.post(f"/v1/uploads/{upload_id}/complete", json=complete_payload)
    assert response.status_code == 200


def test_complete_upload_response_contains_event(app_client: TestClient) -> None:
    init_resp = app_client.post("/v1/uploads", json=_INITIATE_PAYLOAD)
    upload_id = init_resp.json()["upload_id"]
    chunk_count = init_resp.json()["chunk_count"]

    complete_payload = {
        "file_name": "lecture1.pdf",
        "content_type": "application/pdf",
        "chunks": [{"chunk_index": i, "size_bytes": 1024} for i in range(chunk_count)],
        "course_code": "CS101",
        "university_name": "LIU",
    }
    body = app_client.post(f"/v1/uploads/{upload_id}/complete", json=complete_payload).json()
    assert body["upload_id"] == upload_id
    assert body["event_published"] is True
    assert "event_id" in body
    assert "document_id" in body
