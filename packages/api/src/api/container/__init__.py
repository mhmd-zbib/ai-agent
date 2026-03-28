"""Service container — wires all services together on startup and tears them down on shutdown."""

from fastapi import FastAPI

from api.container.academic import (
    create_course_service,
    create_faculty_service,
    create_major_service,
    create_onboarding_service,
    create_university_service,
)
from api.container.chat import create_chat_service
from api.container.documents import create_document_upload_service
from api.container.infra import create_infrastructure
from api.container.users import create_admin_service, create_user_service
from common.core.config import Settings


def startup(app: FastAPI, settings: Settings) -> None:
    """Initialise all services and attach them to app.state."""
    if not hasattr(app.state, "postgres_engine"):
        postgres_engine, redis_client = create_infrastructure(settings)
        app.state.postgres_engine = postgres_engine
        app.state.redis_client = redis_client

    if not hasattr(app.state, "user_service"):
        app.state.user_service = create_user_service(
            settings=settings,
            postgres_engine=app.state.postgres_engine,
        )

    if not hasattr(app.state, "admin_service"):
        app.state.admin_service = create_admin_service(
            user_service=app.state.user_service,
            postgres_engine=app.state.postgres_engine,
        )
        app.state.admin_service.seed_default_admin(
            email=settings.initial_admin_email,
            password=settings.initial_admin_password,
        )

    if not hasattr(app.state, "university_service"):
        app.state.university_service = create_university_service(app.state.postgres_engine)

    if not hasattr(app.state, "faculty_service"):
        app.state.faculty_service = create_faculty_service(app.state.postgres_engine)

    if not hasattr(app.state, "major_service"):
        app.state.major_service = create_major_service(app.state.postgres_engine)

    if not hasattr(app.state, "course_service"):
        app.state.course_service = create_course_service(app.state.postgres_engine)

    if not hasattr(app.state, "onboarding_service"):
        app.state.onboarding_service = create_onboarding_service(
            postgres_engine=app.state.postgres_engine,
            university_service=app.state.university_service,
            faculty_service=app.state.faculty_service,
            major_service=app.state.major_service,
            course_service=app.state.course_service,
        )

    if not hasattr(app.state, "chat_service"):
        app.state.chat_service = create_chat_service(
            settings=settings,
            postgres_engine=app.state.postgres_engine,
            redis_client=app.state.redis_client,
        )

    if not hasattr(app.state, "document_upload_service"):
        app.state.document_upload_service = create_document_upload_service(
            settings=settings,
            redis_client=app.state.redis_client,
        )


def shutdown(app: FastAPI) -> None:
    """Release resources on application shutdown."""
    chat_service = getattr(app.state, "chat_service", None)
    if chat_service is not None:
        chat_service.close()

    user_service = getattr(app.state, "user_service", None)
    if user_service is not None:
        user_service.close()


__all__ = ["startup", "shutdown"]
