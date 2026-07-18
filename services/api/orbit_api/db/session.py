"""Database engine and unit-of-work helpers."""

from collections.abc import Iterator

from orbit_runtime.infrastructure import InfrastructureSettings
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_database_engine(database_url: str | None = None) -> Engine:
    url = database_url or InfrastructureSettings.from_environment().database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True)


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def database_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
