"""AI request log: one row per billed request a user sends to Claude.

It exists to rate-limit AI usage per user (see ``ai_usage_service``), so it
lives in the database rather than in process memory: the count must survive
restarts and be shared by every worker process, or the limit resets on each
deploy and multiplies with the worker count.

``created_at`` is written by the application, not defaulted by the database:
the limiter compares it against the application's clock (injectable in
tests), so both sides of that comparison must come from the same clock.

``feature`` is a plain string rather than an enum. The set of AI features
will grow, and adding a value to a native PostgreSQL enum needs a migration.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiRequest(Base):
    __tablename__ = "ai_requests"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    feature: Mapped[str] = mapped_column(String(50))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # The limiter's only query: "this user's requests since <cutoff>".
    __table_args__ = (
        Index("ix_ai_requests_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<AiRequest id={self.id} user_id={self.user_id} "
            f"{self.feature} at {self.created_at}>"
        )
