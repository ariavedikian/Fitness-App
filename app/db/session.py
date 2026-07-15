"""Database engine and per-request session management."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# SQLite refuses to reuse a connection across threads by default, but the
# threads FastAPI hands us are safe here because each request gets its own
# session. PostgreSQL needs no such accommodation, so the argument is
# applied only for SQLite.
connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(settings.database_url, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency providing a database session for one request.

    The ``finally`` block guarantees the connection is returned to the pool
    even if the route raises.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
