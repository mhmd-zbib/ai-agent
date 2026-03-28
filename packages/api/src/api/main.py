"""FastAPI application — entry point and router registration."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import Response

from api.admin.router import router as admin_router
from api.auth.router import router as auth_router
from api.chat.router import router as chat_router
from api.container import shutdown, startup
from api.courses.router import router as courses_router
from api.documents.router import router as documents_router
from api.faculties.router import router as faculties_router
from api.health.router import router as health_router
from api.majors.router import router as majors_router
from api.onboarding.router import router as onboarding_router
from api.universities.router import router as universities_router
from api.users.router import router as users_router
from common.core.config import get_settings
from common.core.exceptions import register_exception_handlers
from common.core.log_config import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        startup(app, settings)
        try:
            yield
        finally:
            shutdown(app)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.state.settings = settings

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id")
        if request_id:
            request.state.request_id = request_id
        response = await call_next(request)
        if request_id:
            response.headers["x-request-id"] = request_id
        return response

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(admin_router)
    app.include_router(universities_router)
    app.include_router(faculties_router)
    app.include_router(majors_router)
    app.include_router(courses_router)
    app.include_router(onboarding_router)
    app.include_router(chat_router)
    app.include_router(documents_router)
    register_exception_handlers(app)

    return app


app = create_app()
