"""Tests for the exercise catalogue: seed data and search."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.seed import seed_exercises
from app.models import Exercise
from app.services import exercise_service
from app.services.workout import ExerciseType

SIGNUP = {"email": "lifter@example.com", "password": "correct-horse-battery"}


def sign_in(client: TestClient) -> None:
    client.post("/api/auth/register", json=SIGNUP)


def make_exercise(
    name: str,
    type_: ExerciseType = ExerciseType.STRENGTH,
    met: float | None = None,
    muscle_group: str | None = None,
) -> Exercise:
    return Exercise(name=name, type=type_, met=met, muscle_group=muscle_group)


def add(db: Session, *exercises: Exercise) -> None:
    db.add_all(exercises)
    db.commit()


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


# --------------------------------------------------------------- search service
def test_search_matches_name_case_insensitively(db: Session) -> None:
    add(db, make_exercise("Bench Press"), make_exercise("Squat"))

    assert [e.name for e in exercise_service.search_exercises(db, "bench")] == [
        "Bench Press"
    ]


def test_search_matches_muscle_group(db: Session) -> None:
    add(
        db,
        make_exercise("Squat", muscle_group="Legs"),
        make_exercise("Bench Press", muscle_group="Chest"),
    )

    results = exercise_service.search_exercises(db, "legs")

    assert [e.name for e in results] == ["Squat"]


def test_search_ranks_prefix_matches_first(db: Session) -> None:
    add(
        db,
        make_exercise("Bulgarian Split Squat"),
        make_exercise("Squat"),
    )

    names = [e.name for e in exercise_service.search_exercises(db, "squat")]

    assert names.index("Squat") < names.index("Bulgarian Split Squat")


def test_search_blank_query_returns_nothing(db: Session) -> None:
    add(db, make_exercise("Squat"))

    assert exercise_service.search_exercises(db, "   ") == []


# --------------------------------------------------------------- search endpoint
def test_search_endpoint_returns_matches(client: TestClient, db: Session) -> None:
    add(db, make_exercise("Running", ExerciseType.CARDIO, met=9.8))
    sign_in(client)

    response = client.get("/api/exercises/search", params={"q": "run"})

    assert response.status_code == 200
    exercise = response.json()[0]
    assert exercise["name"] == "Running"
    assert exercise["type"] == "cardio"
    assert exercise["met"] == 9.8
    assert exercise["muscle_group"] is None


def test_search_endpoint_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/exercises/search", params={"q": "run"}).status_code == 401
