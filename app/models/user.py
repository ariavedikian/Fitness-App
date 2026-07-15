"""User account model."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


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

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
