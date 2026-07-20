"""Workout routes: add entries, read a day, delete an entry."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User, WorkoutEntry
from app.schemas.workout import (
    DayWorkoutsRead,
    WorkoutEntryCreate,
    WorkoutEntryRead,
)
from app.services import workout_service

router = APIRouter(prefix="/api/workouts", tags=["workouts"])


def _entry_read(entry: WorkoutEntry) -> WorkoutEntryRead:
    return WorkoutEntryRead(
        id=entry.id,
        date=entry.date,
        exercise_name=entry.exercise_name,
        type=entry.type,
        muscle_group=entry.muscle_group,
        sets=entry.sets,
        reps=entry.reps,
        weight_kg=entry.weight_kg,
        duration_minutes=entry.duration_minutes,
        distance_km=entry.distance_km,
        # Round only here, at the display boundary — never mid-calculation.
        calories_burned=(
            round(entry.calories_burned)
            if entry.calories_burned is not None
            else None
        ),
    )


@router.post(
    "",
    response_model=WorkoutEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log an exercise",
)
def create_workout_entry(
    payload: WorkoutEntryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkoutEntryRead:
    try:
        entry = workout_service.create_entry(db, current_user, payload)
    except workout_service.ExerciseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exercise not found."
        ) from exc
    except workout_service.InvalidWorkoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return _entry_read(entry)


@router.get("", response_model=DayWorkoutsRead, summary="Read a day's workouts")
def read_day(
    day: date | None = Query(default=None, alias="date"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DayWorkoutsRead:
    day = day or date.today()
    entries = workout_service.get_day_entries(db, current_user, day)
    return DayWorkoutsRead(
        date=day,
        entries=[_entry_read(e) for e in entries],
        total_calories_burned=round(workout_service.day_total_calories(entries)),
    )


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workout entry",
)
def delete_workout_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not workout_service.delete_entry(db, current_user, entry_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout entry not found.",
        )
