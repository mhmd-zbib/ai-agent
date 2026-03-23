from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.shared.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base exception for expected application errors."""

    status_code = 400
    code = "app_error"


class ConfigurationError(AppError):
    """Raised when runtime configuration is missing or invalid."""

    status_code = 500
    code = "configuration_error"


class UpstreamServiceError(AppError):
    """Raised when an upstream dependency fails."""

    status_code = 502
    code = "upstream_service_error"


class AuthenticationError(AppError):
    """Raised when authentication credentials are invalid or missing."""

    status_code = 401
    code = "authentication_error"


class ConflictError(AppError):
    """Raised when creating a resource conflicts with existing state."""

    status_code = 409
    code = "conflict_error"


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    request_id = _request_id(request)
    payload: dict[str, object] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    headers: dict[str, str] | None = None
    if request_id:
        payload["error"]["request_id"] = request_id
        headers = {"x-request-id": request_id}

    return JSONResponse(status_code=status_code, content=payload, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            f"Application error [{exc.code}]: {str(exc)}",
            extra={
                "request_id": _request_id(request),
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code,
                "error_code": exc.code,
            },
            exc_info=True,
        )
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=str(exc),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = []
        for error in exc.errors():
            field = ".".join(str(x) for x in error["loc"][1:])
            errors.append(f"{field}: {error['msg']}")

        logger.warning(
            f"Validation error: {', '.join(errors)}",
            extra={
                "request_id": _request_id(request),
                "path": request.url.path,
                "method": request.method,
                "status_code": 422,
                "error_code": "validation_error",
                "error_count": len(errors),
            },
        )
        return _error_response(
            request,
            status_code=422,
            code="validation_error",
            message="Invalid request payload.",
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        logger.warning(
            f"HTTP exception [{exc.status_code}]: {detail}",
            extra={
                "request_id": _request_id(request),
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code,
                "error_code": "http_error",
            },
            exc_info=True,
        )
        return _error_response(
            request,
            status_code=exc.status_code,
            code="http_error",
            message=detail,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            f"Unhandled exception [{type(exc).__name__}]: {str(exc)}",
            extra={
                "request_id": _request_id(request),
                "path": request.url.path,
                "method": request.method,
                "status_code": 500,
                "error_code": "internal_server_error",
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
        return _error_response(
            request,
            status_code=500,
            code="internal_server_error",
            message="An unexpected error occurred.",
        )
