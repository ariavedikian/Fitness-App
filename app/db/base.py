"""Declarative base class for all ORM models.

Every model inherits from ``Base``, which is what lets SQLAlchemy (and
Alembic) discover the full schema through ``Base.metadata``.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
