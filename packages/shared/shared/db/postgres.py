from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def create_postgres_engine(
    database_url: str,
    pool_size: int,
    max_overflow: int,
    pool_timeout_seconds: int,
) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout_seconds,
    )
