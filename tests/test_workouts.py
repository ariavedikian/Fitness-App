"""Tests for workout logging: create (with type validation + calorie estimate),
read a day, and delete."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Exercise, Profile, User, WorkoutEntry
from app.services import workout_service
from app.services.nutrition import ActivityLevel, Goal, Sex
from app.services.workout import ExerciseType

SIGNUP = {"email": "athlete@example.com", "password": "correct-horse-battery"}


def sign_in(client: TestClient) -> None:
    client.post("/api/auth/register", json=SIGNUP)


def _current_user(db: Session) -> User:
    return db.scalar(select(User).where(User.email == SIGNUP["email"]))


def give_profile(db: Session, weight_kg: float = 70.0) -> None:
    """Attach a profile (for calorie estimation) to the signed-in user.

    Must be called after ``sign_in`` — the user has to exist first.
    """
    db.add(
        Profile(
            user_id=_current_user(db).id,
            height_cm=178.0,
            weight_kg=weight_kg,
            birth_date=date(1996, 1, 1),
            sex=Sex.MALE,
            activity_level=ActivityLevel.MODERATE,
            goal=Goal.MAINTAIN,
        )
    )
    db.commit()


def add_exercise(
    db: Session,
    name: str,
    type_: ExerciseType,
    met: float | None = None,
    muscle_group: str | None = None,
) -> Exercise:
    exercise = Exercise(name=name, type=type_, met=met, muscle_group=muscle_group)
    db.add(exercise)
    db.commit()
    db.refresh(exercise)
    return exercise


# ------------------------------------------------------------- create (strength)
def test_log_strength_exercise_snapshots_and_clears_cardio(
    client: TestClient, db: Session
) -> None:
    bench = add_exercise(
        db, "Bench Press", ExerciseType.STRENGTH, muscle_group="Chest"
    )
    sign_in(client)

    response = client.post(
        "/api/workouts",
        json={"exercise_id": bench.id, "sets": 3, "reps": 8, "weight_kg": 60},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "strength"
    assert body["exercise_name"] == "Bench Press"
    assert body["muscle_group"] == "Chest"
    assert (body["sets"], body["reps"], body["weight_kg"]) == (3, 8, 60)
    # Cardio columns stay null for a strength entry.
    assert body["duration_minutes"] is None and body["distance_km"] is None
    # No calories were supplied and we don't estimate strength.
    assert body["calories_burned"] is None


def test_bodyweight_strength_needs_no_weight(
    client: TestClient, db: Session
) -> None:
    pushup = add_exercise(
        db, "Push-up", ExerciseType.STRENGTH, muscle_group="Chest"
    )
    sign_in(client)

    response = client.post(
        "/api/workouts", json={"exercise_id": pushup.id, "sets": 3, "reps": 15}
    )

    assert response.status_code == 201
    assert response.json()["weight_kg"] is None


# --------------------------------------------------------------- create (cardio)
def test_log_cardio_estimates_calories_from_met_and_weight(
    client: TestClient, db: Session
) -> None:
    running = add_exercise(db, "Running", ExerciseType.CARDIO, met=8)
    sign_in(client)
    give_profile(db, weight_kg=70)

    response = client.post(
        "/api/workouts", json={"exercise_id": running.id, "duration_minutes": 30}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "cardio"
    # 8 MET * 70 kg * 0.5 h = 280 kcal.
    assert body["calories_burned"] == 280
    assert body["duration_minutes"] == 30
    assert body["sets"] is None and body["reps"] is None


def test_cardio_without_a_profile_leaves_calories_unset(
    client: TestClient, db: Session
) -> None:
    running = add_exercise(db, "Running", ExerciseType.CARDIO, met=8)
    sign_in(client)  # no profile -> no body weight to estimate from

    response = client.post(
        "/api/workouts", json={"exercise_id": running.id, "duration_minutes": 30}
    )

    assert response.status_code == 201
    assert response.json()["calories_burned"] is None


def test_supplied_calories_override_the_estimate(
    client: TestClient, db: Session
) -> None:
    running = add_exercise(db, "Running", ExerciseType.CARDIO, met=8)
    sign_in(client)
    give_profile(db, weight_kg=70)

    response = client.post(
        "/api/workouts",
        json={
            "exercise_id": running.id,
            "duration_minutes": 30,
            "calories_burned": 200,
        },
    )

    # The user's number wins over the 280 kcal estimate.
    assert response.json()["calories_burned"] == 200


# ------------------------------------------------------------------- validation
def test_strength_without_sets_and_reps_is_rejected(
    client: TestClient, db: Session
) -> None:
    bench = add_exercise(
        db, "Bench Press", ExerciseType.STRENGTH, muscle_group="Chest"
    )
    sign_in(client)

    response = client.post(
        "/api/workouts", json={"exercise_id": bench.id, "weight_kg": 60}
    )

    assert response.status_code == 422


def test_cardio_without_duration_is_rejected(
    client: TestClient, db: Session
) -> None:
    running = add_exercise(db, "Running", ExerciseType.CARDIO, met=8)
    sign_in(client)

    response = client.post(
        "/api/workouts", json={"exercise_id": running.id, "distance_km": 5}
    )

    assert response.status_code == 422


def test_log_unknown_exercise_is_404(client: TestClient) -> None:
    sign_in(client)

    response = client.post(
        "/api/workouts", json={"exercise_id": 999, "sets": 3, "reps": 8}
    )

    assert response.status_code == 404


def test_log_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/api/workouts", json={"exercise_id": 1, "sets": 3, "reps": 8}
    )

    assert response.status_code == 401


# --------------------------------------------------------------------- read day
def test_read_day_sums_calories_unrounded(
    client: TestClient, db: Session
) -> None:
    running = add_exercise(db, "Running", ExerciseType.CARDIO, met=8)
    sign_in(client)
    give_profile(db, weight_kg=70)

    client.post(
        "/api/workouts", json={"exercise_id": running.id, "duration_minutes": 30}
    )  # 280
    client.post(
        "/api/workouts", json={"exercise_id": running.id, "duration_minutes": 15}
    )  # 140

    body = client.get("/api/workouts").json()

    assert len(body["entries"]) == 2
    assert body["total_calories_burned"] == 420


def test_read_empty_day(client: TestClient) -> None:
    sign_in(client)

    body = client.get("/api/workouts").json()

    assert body["entries"] == []
    assert body["total_calories_burned"] == 0


# ---------------------------------------------------------------------- delete
def test_delete_own_entry(client: TestClient, db: Session) -> None:
    bench = add_exercise(
        db, "Bench Press", ExerciseType.STRENGTH, muscle_group="Chest"
    )
    sign_in(client)
    entry_id = client.post(
        "/api/workouts", json={"exercise_id": bench.id, "sets": 3, "reps": 8}
    ).json()["id"]

    assert client.delete(f"/api/workouts/{entry_id}").status_code == 204
    assert client.get("/api/workouts").json()["entries"] == []


def test_delete_missing_entry_is_404(client: TestClient) -> None:
    sign_in(client)

    assert client.delete("/api/workouts/999").status_code == 404


def test_delete_rejects_another_users_entry(db: Session) -> None:
    # Service-level so no session juggling: user B must not delete A's entry.
    a = User(email="a@example.com", hashed_password="x")
    b = User(email="b@example.com", hashed_password="x")
    db.add_all([a, b])
    db.commit()
    entry = WorkoutEntry(
        user_id=a.id,
        date=date.today(),
        exercise_name="Bench Press",
        type=ExerciseType.STRENGTH,
        muscle_group="Chest",
        sets=3,
        reps=8,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    assert workout_service.delete_entry(db, b, entry.id) is False
    assert db.get(WorkoutEntry, entry.id) is not None  # still there
