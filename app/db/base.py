"""Declarative base class for all ORM models.

Every model inherits from ``Base``, which is what lets SQLAlchemy (and
Alembic) discover the full schema through ``Base.metadata``.
"""

from sqlalchemy import Enum
from sqlalchemy.orm import DeclarativeBase, MappedColumn, mapped_column


class Base(DeclarativeBase):
    pass


def enum_column(enum_cls: type) -> MappedColumn:
    """A column that persists an enum by its value ("male"), not its name.

    SQLAlchemy stores the member *name* by default; ``values_callable`` makes
    the stored string match the value the API and JSON already use, so the
    database and the wire format never diverge. Shared here because several
    models store enums this way.
    """
    return mapped_column(
        Enum(enum_cls, values_callable=lambda e: [member.value for member in e])
    )
