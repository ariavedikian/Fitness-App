"""User account model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.profile import Profile


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # Only ever stores a one-way hash — the plaintext password is never
    # written to the database or logged.
    hashed_password: Mapped[str] = mapped_column(String(255))

    # Computed by the database rather than Python, so the timestamp is
    # consistent no matter which process inserts the row.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # The matching profile, or None until the user fills it in. delete-orphan
    # means removing a user also removes their profile via the ORM, mirroring
    # the database's ON DELETE CASCADE.
    profile: Mapped[Profile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
