"""Meal log entry: one food, eaten on a day, in a meal.

Nutrition is *snapshotted* — copied from the food into this row at log time —
rather than referenced live. A historical day therefore never changes if the
food is later edited or deleted, and an entry stands on its own even for a
food that was only ever searched, never stored (the future external-API
case). ``food_id`` is kept purely as a soft link for provenance; it is never
the source of the numbers.
"""

from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MealType(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    # SET NULL, not CASCADE: deleting a food must never delete history. The
    # snapshot below keeps the entry fully intact even with no food behind it.
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="SET NULL")
    )

    date: Mapped[date] = mapped_column(Date)
    meal_type: Mapped[MealType] = mapped_column(
        SAEnum(MealType, values_callable=lambda e: [m.value for m in e])
    )
    quantity_grams: Mapped[float] = mapped_column(Float)

    # --- snapshot of the food at the moment it was logged ---
    food_name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(200))
    calories_per_100g: Mapped[float] = mapped_column(Float)
    protein_per_100g: Mapped[float] = mapped_column(Float)
    carbs_per_100g: Mapped[float] = mapped_column(Float)
    fat_per_100g: Mapped[float] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # The hot query is always "this user's entries on this day", so index that
    # exact pair rather than either column alone.
    __table_args__ = (Index("ix_log_entries_user_date", "user_id", "date"),)

    def __repr__(self) -> str:
        return (
            f"<LogEntry id={self.id} user_id={self.user_id} "
            f"{self.food_name!r} {self.quantity_grams}g>"
        )
