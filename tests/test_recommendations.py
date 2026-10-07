"""Tests for AI meal suggestions: the budget the server sends, and the endpoint.

Claude is stubbed at the adapter boundary (``ai_client.recommend_meals``) —
the SDK call itself is covered by ``test_ai_client``. What's tested here is
what the server *asks for*: the remaining budget it computes from goals,
today's meals and workouts, and how each outcome maps to an HTTP response.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.recommendations import _describe_wait
from app.core.config import settings
from app.models import AiRequest, LogEntry, MealType, User, WorkoutEntry
from app.services import ai_client
from app.services.ai_client import AiUnavailableError, MealRequest, MealSuggestion
from app.services.nutrition import Nutrition
from app.services.recommendation_service import MIN_CALORIES_TO_SUGGEST
from app.services.workout import ExerciseType

URL = "/api/recommendations/meals"
SIGNUP = {"email": "hungry@example.com", "password": "correct-horse-battery"}
PROFILE = {
    "height_cm": 180,
    "weight_kg": 80,
    "birth_date": "1996-01-01",
    "sex": "male",
    "activity_level": "moderate",
    "goal": "maintain",
}
SUGGESTION = {
    "name": "Turkey chili",
    "description": "A 400 g bowl of lean turkey and bean chili.",
    "calories": 520,
    "protein_g": 45,
    "carbs_g": 48,
    "fat_g": 14,
}


def sign_in(client: TestClient) -> None:
    client.post("/api/auth/register", json=SIGNUP)


def set_up_profile(client: TestClient) -> dict:
    """Create the profile and return the goals it yields. Goals depend on
    today's date (via age), so tests read them rather than hard-code them."""
    client.put("/api/profile", json=PROFILE)
    return client.get("/api/profile/goals").json()


def _user_id(db: Session) -> int:
    return db.scalar(select(User.id).where(User.email == SIGNUP["email"]))


def add_meal(db: Session, grams: float, day: date | None = None) -> None:
    """Log a food that is 100 kcal / 10 P / 20 C / 4 F per 100 g, so grams
    equal kilocalories and the macro arithmetic stays readable."""
    db.add(
        LogEntry(
            user_id=_user_id(db),
            food_id=None,
            date=day or date.today(),
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


def add_workout(db: Session, burned: float, day: date | None = None) -> None:
    db.add(
        WorkoutEntry(
            user_id=_user_id(db),
            date=day or date.today(),
            exercise_name="Running",
            type=ExerciseType.CARDIO,
            muscle_group=None,
            duration_minutes=30,
            calories_burned=burned,
        )
    )
    db.commit()


@pytest.fixture
def claude(monkeypatch: pytest.MonkeyPatch) -> list[MealRequest]:
    """Stand in for Claude: record each request, answer with SUGGESTION."""
    requests: list[MealRequest] = []

    def fake_recommend(request: MealRequest) -> list[MealSuggestion]:
        requests.append(request)
        return [MealSuggestion(**SUGGESTION)]

    monkeypatch.setattr(ai_client, "recommend_meals", fake_recommend)
    return requests


# ------------------------------------------------------------ the budget sent
def test_sends_claude_the_remaining_budget(
    client: TestClient, db: Session, ai_on: None, claude: list[MealRequest]
) -> None:
    sign_in(client)
    goals = set_up_profile(client)
    add_meal(db, grams=200)  # 200 kcal, 20 P, 40 C, 8 F
    add_workout(db, burned=300)

    response = client.post(URL, json={"meal_type": "dinner"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "suggestions": [SUGGESTION]}
    (request,) = claude
    assert request.meal_type is MealType.DINNER
    macros = goals["macros"]
    # Net calories: goal − 200 eaten + 300 burned = goal + 100.
    # Macros: goal − eaten only; the run gives back no grams.
    assert request.remaining == Nutrition(
        calories=goals["calories"] + 100,
        protein_g=macros["protein_g"] - 20,
        carbs_g=macros["carbs_g"] - 40,
        fat_g=macros["fat_g"] - 8,
    )


def test_only_todays_log_counts(
    client: TestClient, db: Session, ai_on: None, claude: list[MealRequest]
) -> None:
    sign_in(client)
    goals = set_up_profile(client)
    yesterday = date.today() - timedelta(days=1)
    add_meal(db, grams=500, day=yesterday)
    add_workout(db, burned=400, day=yesterday)

    client.post(URL, json={})

    # Nothing logged today, so the whole day's goals remain.
    assert claude[0].remaining.calories == goals["calories"]
    assert claude[0].remaining.protein_g == goals["macros"]["protein_g"]


def test_meal_type_is_optional(
    client: TestClient, ai_on: None, claude: list[MealRequest]
) -> None:
    sign_in(client)
    set_up_profile(client)

    assert client.post(URL, json={}).status_code == 200
    assert claude[0].meal_type is None


def test_unknown_meal_type_is_rejected(
    client: TestClient, ai_on: None, claude: list[MealRequest]
) -> None:
    sign_in(client)
    set_up_profile(client)

    assert client.post(URL, json={"meal_type": "brunch"}).status_code == 422
    assert claude == []


# ---------------------------------------------------------- a spent budget
@pytest.mark.parametrize(
    "calories_left, expected_status, claude_calls",
    [
        (MIN_CALORIES_TO_SUGGEST - 1, "budget_spent", 0),
        (MIN_CALORIES_TO_SUGGEST, "ok", 1),
    ],
)
def test_a_spent_budget_skips_the_call(
    client: TestClient,
    db: Session,
    ai_on: None,
    claude: list[MealRequest],
    calories_left: int,
    expected_status: str,
    claude_calls: int,
) -> None:
    sign_in(client)
    goals = set_up_profile(client)
    add_meal(db, grams=goals["calories"] - calories_left)  # grams == kcal

    response = client.post(URL, json={})

    assert response.status_code == 200
    assert response.json()["status"] == expected_status
    assert len(claude) == claude_calls


def test_spent_budget_returns_no_suggestions(
    client: TestClient, db: Session, ai_on: None, claude: list[MealRequest]
) -> None:
    sign_in(client)
    goals = set_up_profile(client)
    add_meal(db, grams=goals["calories"] + 300)  # 300 kcal over

    assert client.post(URL, json={}).json() == {
        "status": "budget_spent",
        "suggestions": [],
    }


# ------------------------------------------------------- errors and access
def test_requires_login(client: TestClient) -> None:
    assert client.post(URL, json={}).status_code == 401


def test_turned_off_returns_503_without_calling_claude(
    client: TestClient, claude: list[MealRequest]
) -> None:
    sign_in(client)
    set_up_profile(client)

    response = client.post(URL, json={})

    assert response.status_code == 503
    assert "turned off" in response.json()["detail"]
    assert claude == []


def test_without_a_profile_returns_409(
    client: TestClient, ai_on: None, claude: list[MealRequest]
) -> None:
    sign_in(client)

    response = client.post(URL, json={})

    assert response.status_code == 409
    assert "profile" in response.json()["detail"]
    assert claude == []


def test_claude_failure_returns_503(
    client: TestClient, ai_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(client)
    set_up_profile(client)

    def failing(request: MealRequest) -> list[MealSuggestion]:
        raise AiUnavailableError("overloaded")

    monkeypatch.setattr(ai_client, "recommend_meals", failing)

    response = client.post(URL, json={})

    assert response.status_code == 503
    assert "try again" in response.json()["detail"]


# ------------------------------------------------------------ rate limiting
def ai_requests_stored(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AiRequest))


def test_rate_limited_once_the_allowance_is_used(
    client: TestClient,
    ai_on: None,
    claude: list[MealRequest],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ai_daily_limit", 2)
    sign_in(client)
    set_up_profile(client)

    allowed = [client.post(URL, json={}).status_code for _ in range(2)]
    blocked = client.post(URL, json={})

    assert allowed == [200, 200]
    assert blocked.status_code == 429
    # Both requests were seconds ago, so the wait is just under 24 hours.
    assert 23 * 3600 < int(blocked.headers["Retry-After"]) <= 24 * 3600
    assert "Try again in about 24 hours" in blocked.json()["detail"]
    assert len(claude) == 2  # the blocked request never reached Claude


def test_a_spent_budget_does_not_use_the_allowance(
    client: TestClient,
    db: Session,
    ai_on: None,
    claude: list[MealRequest],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ai_daily_limit", 1)
    sign_in(client)
    goals = set_up_profile(client)
    add_meal(db, grams=goals["calories"] + 300)

    statuses = [client.post(URL, json={}).json()["status"] for _ in range(3)]

    assert statuses == ["budget_spent"] * 3  # never a 429
    assert ai_requests_stored(db) == 0


def test_a_failed_call_still_counts(
    client: TestClient,
    db: Session,
    ai_on: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A failed call may still have been billed, and the limit protects the bill.
    sign_in(client)
    set_up_profile(client)

    def failing(request: MealRequest) -> list[MealSuggestion]:
        raise AiUnavailableError("timed out")

    monkeypatch.setattr(ai_client, "recommend_meals", failing)

    assert client.post(URL, json={}).status_code == 503
    assert ai_requests_stored(db) == 1


@pytest.mark.parametrize(
    "seconds, wording",
    [
        (1, "about a minute"),
        (60, "about a minute"),
        (61, "about 2 minutes"),
        (3599, "about an hour"),  # rounds up: 59 min 59 s is not "59 minutes"
        (3600, "about an hour"),
        (3601, "about 2 hours"),
        (86_400, "about 24 hours"),
    ],
)
def test_wait_is_described_rounding_up(seconds: int, wording: str) -> None:
    assert _describe_wait(seconds) == wording
