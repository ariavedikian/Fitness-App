"""Body-weight entry: one weigh-in on a day — the raw time-series behind
progress tracking.

Unlike meal and workout logging, there is no catalogue row to snapshot or
protect: a weigh-in is a plain user-owned fact. So ``user_id`` deletes with
``CASCADE`` (no soft link), and there is no descriptive snapshot to keep.

At most one weigh-in per day: the unique ``(user_id, date)`` constraint makes
"today's weight" unambiguous and lets the service upsert a re-logged day. That
same constraint is index-backed, so it also serves the hot "this user's
weigh-ins over time" query — one constraint doing both jobs.
"""

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WeightEntry(Base):
    __tablename__ = "weight_entries"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    date: Mapped[date] = mapped_column(Date)
    weight_kg: Mapped[float] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # One weigh-in per user per day. A unique constraint is index-backed, so it
    # both enforces the rule and serves the "this user's weigh-ins over time"
    # query — no separate Index needed.
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_weight_entries_user_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<WeightEntry id={self.id} user_id={self.user_id} "
            f"{self.date} {self.weight_kg}kg>"
        )
