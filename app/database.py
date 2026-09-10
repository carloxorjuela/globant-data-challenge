from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


@lru_cache
def get_engine() -> Engine:
    """
    Build the engine on first use rather than at import time.

    Importing a module should not open connections. Building it eagerly also
    meant DATABASE_URL was read the moment anything imported this file, before
    a test run had a chance to redirect it, which is how a suite ends up
    truncating the database it was explicitly pointed away from.
    """
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with get_session_factory()() as session:
        yield session
