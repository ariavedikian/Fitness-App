"""Exercise model: a searchable catalogue entry, the workout counterpart of Food.

An exercise is a *definition* ("Running", "Bench Press"), not a performance —
what the user actually did is a ``WorkoutLogEntry`` that snapshots the relevant
fields at log time, exactly as meal logging snapshots a food.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, enum_column
from app.services.workout import ExerciseType


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(200), index=True)

    type: Mapped[ExerciseType] = enum_column(ExerciseType)

    # MET (kcal per kg per hour) drives the cardio calorie estimate. NULL when
    # we don't estimate — most strength work, where calories aren't the point
    # and there's no duration to base an estimate on.
    met: Mapped[float | None] = mapped_column(Float)

    # e.g. "Chest", "Legs" for strength; NULL for cardio. Used for display and
    # grouping, not required by any calculation.
    muscle_group: Mapped[str | None] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Exercise id={self.id} {self.name!r} {self.type.value}>"
