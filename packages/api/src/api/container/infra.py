"""Infrastructure factory — postgres engine and redis client."""

from redis import Redis
from sqlalchemy.engine import Engine

from common.core.config import Settings
from common.core.exceptions import ConfigurationError
from common.infra.db.postgres import create_postgres_engine
from common.infra.db.redis import create_redis_client


def create_infrastructure(settings: Settings) -> tuple[Engine, Redis]:
    if not settings.database_url:
        raise ConfigurationError("DATABASE_URL is required.")
    if not settings.redis_url:
        raise ConfigurationError("REDIS_URL is required.")

    postgres_engine = create_postgres_engine(
        database_url=settings.database_url,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_timeout_seconds=settings.postgres_pool_timeout_seconds,
    )
    redis_client = create_redis_client(settings.redis_url)
    return postgres_engine, redis_client
