"""Tests for the exercise catalogue (seed data and, later, search)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.seed import seed_exercises
from app.models import Exercise
from app.services.workout import ExerciseType


def test_seed_exercises_is_idempotent(db: Session) -> None:
    first = seed_exercises(db)
    second = seed_exercises(db)

    assert first > 0  # the empty test database gets populated
    assert second == 0  # a second run adds nothing


def test_seeded_rows_have_type_appropriate_fields(db: Session) -> None:
    seed_exercises(db)

    cardio = db.scalars(
        select(Exercise).where(Exercise.type == ExerciseType.CARDIO)
    ).all()
    strength = db.scalars(
        select(Exercise).where(Exercise.type == ExerciseType.STRENGTH)
    ).all()

    # Cardio drives calorie estimates (needs a MET) and has no muscle group;
    # strength is the mirror image.
    assert cardio and all(e.met and e.met > 0 and e.muscle_group is None for e in cardio)
    assert strength and all(e.met is None and e.muscle_group for e in strength)
