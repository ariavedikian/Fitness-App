"""Shared pytest fixtures.

pytest discovers this file automatically; any fixture defined here can be
requested by name as an argument in any test.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.db.base import Base


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """A throwaway in-memory database, built fresh for each test.

    Tests never touch the real fittrack.db file, so they cannot corrupt
    development data and cannot leak state into one another.
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
