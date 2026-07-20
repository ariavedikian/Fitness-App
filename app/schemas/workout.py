"""Pydantic schemas for exercises and workout logging."""

import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.workout import ExerciseType

# Generous upper bounds to catch fat-finger input without rejecting a
# legitimately hard session.
MAX_SETS = 100
MAX_REPS = 1000
MAX_WEIGHT_KG = 1000
MAX_DURATION_MINUTES = 1440  # 24 hours
MAX_DISTANCE_KM = 1000
MAX_CALORIES = 50_000


class ExerciseRead(BaseModel):
    """An exercise as returned by search."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: ExerciseType
    met: float | None
    muscle_group: str | None


class WorkoutEntryCreate(BaseModel):
    """Request to log an exercise.

    The client sends only the metrics; the server looks up the exercise's
    ``type`` and enforces that the right ones are present (strength needs
    ``sets`` + ``reps``; cardio needs ``duration_minutes``). Field bounds here
    just catch nonsense values — the type-dependent rules live in the service,
    which is the only layer that knows the exercise's type.
    """

    exercise_id: int
    # datetime.date, spelled out because a field named `date` would otherwise
    # shadow the type in its own annotation. Defaults to today on the server.
    date: datetime.date | None = None

    # Strength metrics.
    sets: int | None = Field(default=None, gt=0, le=MAX_SETS)
    reps: int | None = Field(default=None, gt=0, le=MAX_REPS)
    weight_kg: float | None = Field(default=None, gt=0, le=MAX_WEIGHT_KG)

    # Cardio metrics.
    duration_minutes: float | None = Field(
        default=None, gt=0, le=MAX_DURATION_MINUTES
    )
    distance_km: float | None = Field(default=None, ge=0, le=MAX_DISTANCE_KM)

    # Optional override: cardio calories are estimated server-side when omitted.
    calories_burned: float | None = Field(default=None, ge=0, le=MAX_CALORIES)


class WorkoutEntryRead(BaseModel):
    """One logged exercise. Only the columns relevant to its ``type`` are set;
    the rest are null. ``calories_burned`` is rounded for display."""

    id: int
    date: datetime.date
    exercise_name: str
    type: ExerciseType
    muscle_group: str | None
    sets: int | None
    reps: int | None
    weight_kg: float | None
    duration_minutes: float | None
    distance_km: float | None
    calories_burned: int | None


class DayWorkoutsRead(BaseModel):
    """Everything logged on one day, plus the day's total calories burned."""

    date: datetime.date
    entries: list[WorkoutEntryRead]
    total_calories_burned: int
