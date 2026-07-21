"""Tests for the daily analytics aggregation endpoint."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LogEntry, MealType, User, WorkoutEntry
from app.services.workout import ExerciseType

SIGNUP = {"email": "tracker@example.com", "password": "correct-horse-battery"}


def sign_in(client: TestClient) -> None:
    client.post("/api/auth/register", json=SIGNUP)


def _current_user(db: Session) -> User:
    return db.scalar(select(User).where(User.email == SIGNUP["email"]))


def add_log(db: Session, user_id: int, day: date, grams: float = 100.0) -> None:
    """A meal entry of a food that is 100 kcal / 10 P / 20 C / 4 F per 100 g,
    so a gram amount scales to clean round numbers."""
    db.add(
        LogEntry(
            user_id=user_id,
            food_id=None,
            date=day,
            meal_type=MealType.LUNCH,
            quantity_grams=grams,
            food_name="Test Food",
            brand=None,
            calories_per_100g=100.0,
            protein_per_100g=10.0,
            carbs_per_100g=20.0,
            fat_per_100g=4.0,
        )
    )
    db.commit()


def add_workout(db: Session, user_id: int, day: date, burned: float) -> None:
    db.add(
        WorkoutEntry(
            user_id=user_id,
            date=day,
            exercise_name="Running",
            type=ExerciseType.CARDIO,
            muscle_group=None,
            duration_minutes=30,
            calories_burned=burned,
        )
    )
    db.commit()


# ------------------------------------------------------------- aggregation
def test_daily_totals_sum_meals_per_day(client: TestClient, db: Session) -> None:
    sign_in(client)
    uid = _current_user(db).id
    today = date.today()
    # Two meals on one day: 150 g + 100 g = 250 g of the test food.
    add_log(db, uid, today, grams=150)
    add_log(db, uid, today, grams=100)

    entries = client.get("/api/analytics/daily").json()["entries"]

    assert len(entries) == 1
    day = entries[0]
    assert day["date"] == today.isoformat()
    # 250 g → 2.5× per-100 g: 250 kcal, 25 P, 50 C, 10 F.
    assert (day["calories"], day["protein_g"], day["carbs_g"], day["fat_g"]) == (
        250,
        25,
        50,
        10,
    )
    assert day["calories_burned"] == 0
    assert day["net_calories"] == 250


def test_net_calories_subtract_workout_burn(
    client: TestClient, db: Session
) -> None:
    sign_in(client)
    uid = _current_user(db).id
    today = date.today()
    add_log(db, uid, today, grams=200)  # 200 kcal
    add_workout(db, uid, today, burned=50)

    day = client.get("/api/analytics/daily").json()["entries"][0]

    assert day["calories"] == 200
    assert day["calories_burned"] == 50
    assert day["net_calories"] == 150


def test_results_are_oldest_first(client: TestClient, db: Session) -> None:
    sign_in(client)
    uid = _current_user(db).id
    today = date.today()
    add_log(db, uid, today)
    add_log(db, uid, today - timedelta(days=3))
    add_log(db, uid, today - timedelta(days=1))

    dates = [e["date"] for e in client.get("/api/analytics/daily").json()["entries"]]

    assert dates == sorted(dates)


def test_days_without_meals_are_omitted(
    client: TestClient, db: Session
) -> None:
    """A day with only a workout is 'not tracked' for nutrition, not a zero —
    it must not appear in the calorie/macro series."""
    sign_in(client)
    uid = _current_user(db).id
    today = date.today()
    add_log(db, uid, today)
    add_workout(db, uid, today - timedelta(days=1), burned=300)  # no meal

    entries = client.get("/api/analytics/daily").json()["entries"]

    assert [e["date"] for e in entries] == [today.isoformat()]


def test_window_excludes_days_outside_range(
    client: TestClient, db: Session
) -> None:
    sign_in(client)
    uid = _current_user(db).id
    today = date.today()
    add_log(db, uid, today)
    add_log(db, uid, today - timedelta(days=40))  # older than a 30-day window

    entries = client.get("/api/analytics/daily?days=30").json()["entries"]

    assert [e["date"] for e in entries] == [today.isoformat()]


def test_wider_window_includes_the_older_day(
    client: TestClient, db: Session
) -> None:
    sign_in(client)
    uid = _current_user(db).id
    today = date.today()
    add_log(db, uid, today - timedelta(days=40))

    body = client.get("/api/analytics/daily?days=90").json()

    assert body["days"] == 90
    assert len(body["entries"]) == 1


def test_empty_history(client: TestClient) -> None:
    sign_in(client)

    assert client.get("/api/analytics/daily").json() == {"days": 30, "entries": []}


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/analytics/daily").status_code == 401


def test_days_param_is_bounded(client: TestClient) -> None:
    sign_in(client)

    assert client.get("/api/analytics/daily?days=0").status_code == 422
    assert client.get("/api/analytics/daily?days=400").status_code == 422
