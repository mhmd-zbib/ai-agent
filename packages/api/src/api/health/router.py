from fastapi import APIRouter, status

router = APIRouter(tags=["health"])


@router.get(
    "/",
    summary="Root endpoint",
    description="Returns a welcome message confirming the API is running.",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def root() -> dict[str, str]:
    return {
        "message": "Agent Assistant API is running",
        "chat_endpoint": "/v1/agent/chat",
    }


@router.get(
    "/health",
    summary="Health check",
    description="Returns the service health status.",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
async def health() -> dict[str, str]:
    return {"status": "ok"}
