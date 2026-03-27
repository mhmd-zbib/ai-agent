"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter, status

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Health check",
    description="Returns a simple liveness response. Use this for load-balancer health probes.",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "pipeline"}
