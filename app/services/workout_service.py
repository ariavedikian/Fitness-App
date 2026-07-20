"""Business logic for workout logging.

Mirrors ``log_service``: snapshot the catalogue row into the entry at log time,
so history is immutable. Adds one wrinkle meal logging doesn't have — the
exercise's ``type`` decides which metrics are required, and cardio calories are
estimated from the exercise's MET and the user's body weight when not supplied.
"""

from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Exercise, User, WorkoutEntry
from app.schemas.workout import WorkoutEntryCreate
from app.services import profile_service, workout
from app.services.workout import ExerciseType


class ExerciseNotFoundError(Exception):
    """Raised when logging references an exercise that does not exist."""


class InvalidWorkoutError(Exception):
    """Raised when the metrics don't match the exercise type.

    Carries a human-readable message the API surfaces (e.g. "Cardio exercises
    need a duration.").
    """


def _estimate_calories(
    db: Session, user: User, exercise: Exercise, minutes: float
) -> float | None:
    """Estimate calories for a cardio exercise, or ``None`` if we can't.

    Needs both the exercise's MET and the user's body weight; without a profile
    (or an exercise with no MET) we simply don't estimate — the same
    degrade-don't-break stance as the external food search.
    """
    profile = profile_service.get_profile(db, user)
    if profile is None or exercise.met is None:
        return None
    return workout.estimate_calories_burned(
        met=exercise.met, weight_kg=profile.weight_kg, minutes=minutes
    )


def create_entry(
    db: Session, user: User, payload: WorkoutEntryCreate
) -> WorkoutEntry:
    """Log an exercise, snapshotting its descriptive fields into the entry.

    Validates the metrics against the exercise's type and clears the ones that
    don't apply, so a strength row never carries a stray distance and vice
    versa. Cardio calories are estimated when the client doesn't supply them.
    """
    exercise = db.get(Exercise, payload.exercise_id)
    if exercise is None:
        raise ExerciseNotFoundError(payload.exercise_id)

    sets = reps = weight_kg = None
    duration_minutes = distance_km = None
    calories_burned = payload.calories_burned

    if exercise.type == ExerciseType.STRENGTH:
        if payload.sets is None or payload.reps is None:
            raise InvalidWorkoutError("Strength exercises need sets and reps.")
        sets, reps, weight_kg = payload.sets, payload.reps, payload.weight_kg
    else:  # CARDIO
        if payload.duration_minutes is None:
            raise InvalidWorkoutError("Cardio exercises need a duration.")
        duration_minutes, distance_km = payload.duration_minutes, payload.distance_km
        if calories_burned is None:
            calories_burned = _estimate_calories(
                db, user, exercise, duration_minutes
            )

    entry = WorkoutEntry(
        user_id=user.id,
        exercise_id=exercise.id,
        date=payload.date or date_type.today(),
        # Snapshot: copied now, never read back from `exercise`.
        exercise_name=exercise.name,
        type=exercise.type,
        muscle_group=exercise.muscle_group,
        sets=sets,
        reps=reps,
        weight_kg=weight_kg,
        duration_minutes=duration_minutes,
        distance_km=distance_km,
        calories_burned=calories_burned,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_day_entries(
    db: Session, user: User, day: date_type
) -> list[WorkoutEntry]:
    stmt = (
        select(WorkoutEntry)
        .where(WorkoutEntry.user_id == user.id, WorkoutEntry.date == day)
        .order_by(WorkoutEntry.created_at, WorkoutEntry.id)
    )
    return list(db.scalars(stmt))


def delete_entry(db: Session, user: User, entry_id: int) -> bool:
    """Delete one of the user's own entries. Returns False if it is missing or
    belongs to someone else — the caller turns both into a 404 so the endpoint
    never confirms another user's entry exists."""
    entry = db.get(WorkoutEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        return False

    db.delete(entry)
    db.commit()
    return True


def day_total_calories(entries: list[WorkoutEntry]) -> float:
    """Sum calories burned across entries, unrounded, for one rounding at the
    end (entries with no calorie figure count as zero)."""
    return sum(e.calories_burned or 0.0 for e in entries)
