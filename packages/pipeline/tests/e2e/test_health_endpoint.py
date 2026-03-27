"""E2E tests for the health check endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health_returns_ok(app_client: TestClient) -> None:
    response = app_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "pipeline"
