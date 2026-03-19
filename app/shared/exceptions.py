from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base exception for expected application errors."""


class ConfigurationError(AppError):
    """Raised when runtime configuration is missing or invalid."""


class UpstreamServiceError(AppError):
    """Raised when an upstream dependency fails."""


class AuthenticationError(AppError):
    """Raised when authentication credentials are invalid or missing."""


class ConflictError(AppError):
    """Raised when creating a resource conflicts with existing state."""


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

    @app.exception_handler(AuthenticationError)
    async def authentication_error_handler(
        request: Request,  # noqa: ARG001
        exc: AuthenticationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict_error_handler(
        request: Request,  # noqa: ARG001
        exc: ConflictError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(AppError)
    async def app_error_handler(
        request: Request,  # noqa: ARG001
        exc: AppError,
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
