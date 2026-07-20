"""Workout entry: one exercise performed on a day — the workout counterpart of
the meal ``LogEntry``.

Like meal logging, the exercise's descriptive fields are *snapshotted* into the
row at log time, so a historical workout never changes if the exercise is later
edited or deleted, and the entry stands on its own. ``exercise_id`` is a soft
link (SET NULL) kept only for provenance.

One table holds both shapes of exercise. ``type`` says which columns are
meaningful: strength fills ``sets``/``reps``/``weight_kg``; cardio fills
``duration_minutes``/``distance_km``. The unused columns stay NULL, and the
schema layer enforces that the right ones are present for each type.
"""

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, enum_column
from app.services.workout import ExerciseType


class WorkoutEntry(Base):
    __tablename__ = "workout_entries"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    # SET NULL, not CASCADE: deleting an exercise from the catalogue must never
    # delete a user's history. The snapshot below keeps the entry intact.
    exercise_id: Mapped[int | None] = mapped_column(
        ForeignKey("exercises.id", ondelete="SET NULL")
    )

    date: Mapped[date] = mapped_column(Date)

    # --- snapshot of the exercise at the moment it was logged ---
    exercise_name: Mapped[str] = mapped_column(String(200))
    type: Mapped[ExerciseType] = enum_column(ExerciseType)
    muscle_group: Mapped[str | None] = mapped_column(String(100))

    # --- strength metrics (NULL for cardio) ---
    # weight_kg stays nullable even for strength: bodyweight moves (push-ups,
    # planks) have sets and reps but no external load.
    sets: Mapped[int | None] = mapped_column(Integer)
    reps: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[float | None] = mapped_column(Float)

    # --- cardio metrics (NULL for strength) ---
    duration_minutes: Mapped[float | None] = mapped_column(Float)
    distance_km: Mapped[float | None] = mapped_column(Float)

    # Estimated (from MET + body weight) or user-entered, then snapshotted so it
    # never shifts if the exercise's MET or the user's weight later changes.
    calories_burned: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # The hot query is "this user's entries on this day" — the same shape as the
    # meal log, so index the same pair.
    __table_args__ = (Index("ix_workout_entries_user_date", "user_id", "date"),)

    def __repr__(self) -> str:
        return (
            f"<WorkoutEntry id={self.id} user_id={self.user_id} "
            f"{self.exercise_name!r} {self.type.value}>"
        )
