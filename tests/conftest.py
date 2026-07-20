"""Shared pytest fixtures.

pytest discovers this file automatically; any fixture defined here can be
requested by name as an argument in any test.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch the real Open Food Facts API from the test suite.

    OFF is disabled by default so hybrid search runs local-only and no test
    depends on a live third party. Tests that exercise the OFF path re-enable
    it and stub ``off_client.search_off`` / ``fetch_off_product`` themselves.
    """
    monkeypatch.setattr(settings, "off_enabled", False)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """A throwaway in-memory database, built fresh for each test.

    Tests never touch the real fittrack.db file, so they cannot corrupt
    development data and cannot leak state into one another.
    """
    # An in-memory SQLite database belongs to its connection: open a second
    # connection and you get a second, empty database. StaticPool hands out
    # one shared connection instead, so the schema created here is the same
    # schema the app sees when FastAPI runs a route on a worker thread.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    """A test client whose routes talk to the throwaway ``db`` above.

    ``dependency_overrides`` swaps out ``get_db`` for one that hands back the
    test session — the payoff of injecting the session as a dependency rather
    than importing it inside the routes.
    """
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
