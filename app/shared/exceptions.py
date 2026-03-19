from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base exception for expected application errors."""


class ConfigurationError(AppError):
    """Raised when runtime configuration is missing or invalid."""


class UpstreamServiceError(AppError):
    """Raised when an upstream dependency fails."""


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ConfigurationError)
    async def configuration_error_handler(
        request: Request,  # noqa: ARG001
        exc: ConfigurationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(UpstreamServiceError)
    async def upstream_error_handler(
        request: Request,  # noqa: ARG001
        exc: UpstreamServiceError,
    ) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(AppError)
    async def app_error_handler(
        request: Request,  # noqa: ARG001
        exc: AppError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

