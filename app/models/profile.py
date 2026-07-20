"""User profile: the body stats that drive calorie and macro goals.

Kept in its own table rather than piled onto ``users`` because it answers a
different question (who you are physically vs. how you sign in) and because a
brand-new account has no profile yet — separating them keeps every column
here meaningfully non-null.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, enum_column
from app.services.nutrition import ActivityLevel, Goal, Sex

if TYPE_CHECKING:
    from app.models.user import User


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)

    # One row per user: the unique constraint is what makes this a one-to-one
    # relationship rather than one-to-many. ondelete CASCADE lets the database
    # remove the profile automatically when the account is deleted.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    height_cm: Mapped[float] = mapped_column(Float)
    weight_kg: Mapped[float] = mapped_column(Float)
    birth_date: Mapped[date] = mapped_column(Date)

    sex: Mapped[Sex] = enum_column(Sex)
    activity_level: Mapped[ActivityLevel] = enum_column(ActivityLevel)
    goal: Mapped[Goal] = enum_column(Goal)

    # Set on insert and refreshed on every update, so the UI can always show
    # when the stats were last touched.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="profile")

    def __repr__(self) -> str:
        return f"<Profile user_id={self.user_id}>"
