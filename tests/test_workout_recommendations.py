"""Tests for AI workout ideas: what the server asks for, and the endpoint.

Claude is stubbed at the adapter boundary (``ai_client.recommend_workout``) —
the SDK call and the catalogue-built schema are covered by ``test_ai_client``.
What's tested here is the request the server builds (the catalogue, the last
week's workouts, the profile's goal and activity level), how Claude's picks
are resolved to catalogue rows, and how each outcome maps to HTTP.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.seed import seed_exercises
from app.models import AiRequest, Exercise, User
from app.services import ai_client, ai_usage_service, recommendation_service
from app.services.ai_client import (
    AiUnavailableError,
    PastWorkout,
    SuggestedExercise,
    WorkoutRequest,
    WorkoutSuggestion,
)
from app.services.nutrition import ActivityLevel, Goal
from app.services.workout import ExerciseType, WorkoutFocus

URL = "/api/recommendations/workouts"
SIGNUP = {"email": "lifter@example.com", "password": "correct-horse-battery"}
PROFILE = {
    "height_cm": 170,
    "weight_kg": 65,
    "birth_date": "1990-06-15",
    "sex": "female",
    "activity_level": "moderate",
    "goal": "lose",
}
CARDIO, STRENGTH = ExerciseType.CARDIO, ExerciseType.STRENGTH

IDEA = WorkoutSuggestion(
    title="Upper-body strength",
    summary="Your legs worked yesterday, so this trains the chest.",
    exercises=(
        SuggestedExercise("Walking", CARDIO, None, None, 5, "Easy pace."),
        SuggestedExercise("Bench Press", STRENGTH, 3, 10, None, ""),
    ),
)


def sign_in(client: TestClient, email: str = SIGNUP["email"]) -> None:
    """Register (which also signs in) — a second email switches the session
    to a second user."""
    client.post("/api/auth/register", json={**SIGNUP, "email": email})


def ai_requests_stored(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AiRequest))


@pytest.fixture
def catalogue(db: Session) -> dict[str, Exercise]:
    """The real seeded catalogue, by name."""
    seed_exercises(db)
    return {e.name: e for e in db.scalars(select(Exercise))}


def log(
    client: TestClient,
    catalogue: dict[str, Exercise],
    name: str,
    days_ago: int = 0,
    **metrics: float,
) -> None:
    """Log a workout through the real endpoint, so the history the service
    reads is shaped exactly as production writes it."""
    day = date.today() - timedelta(days=days_ago)
    response = client.post(
        "/api/workouts",
        json={"exercise_id": catalogue[name].id, "date": day.isoformat(), **metrics},
    )
    assert response.status_code == 201


@pytest.fixture
def claude(monkeypatch: pytest.MonkeyPatch) -> list[WorkoutRequest]:
    """Stand in for Claude: record each request, answer with IDEA."""
    requests: list[WorkoutRequest] = []

    def fake_recommend(request: WorkoutRequest) -> WorkoutSuggestion:
        requests.append(request)
        return IDEA

    monkeypatch.setattr(ai_client, "recommend_workout", fake_recommend)
    return requests


# --------------------------------------------------------------- the answer
def test_returns_catalogue_exercises_ready_to_log(
    client: TestClient,
    ai_on: None,
    catalogue: dict[str, Exercise],
    claude: list[WorkoutRequest],
) -> None:
    sign_in(client)

    response = client.post(URL, json={})

    assert response.status_code == 200
    walking, bench = catalogue["Walking"], catalogue["Bench Press"]
    # Each exercise is our row (id, type, MET) — what the log dialog needs —
    # not text from Claude.
    assert response.json() == {
        "title": "Upper-body strength",
        "summary": "Your legs worked yesterday, so this trains the chest.",
        "exercises": [
            {
                "exercise": {
                    "id": walking.id,
                    "name": "Walking",
                    "type": "cardio",
                    "met": walking.met,
                    "muscle_group": None,
                },
                "sets": None,
                "reps": None,
                "minutes": 5,
                "note": "Easy pace.",
            },
            {
                "exercise": {
                    "id": bench.id,
                    "name": "Bench Press",
                    "type": "strength",
                    "met": None,
                    "muscle_group": "Chest",
                },
                "sets": 3,
                "reps": 10,
                "minutes": None,
                "note": "",
            },
        ],
    }


# ----------------------------------------------------------- what's sent
def test_sends_the_whole_catalogue_sorted_by_name(
    client: TestClient,
    ai_on: None,
    catalogue: dict[str, Exercise],
    claude: list[WorkoutRequest],
) -> None:
    sign_in(client)

    client.post(URL, json={})

    # Sorted, so the schema built from it doesn't change between requests.
    sent = claude[0].catalogue
    assert [e.name for e in sent] == sorted(catalogue)
    squat = next(e for e in sent if e.name == "Squat")
    assert (squat.type, squat.muscle_group) == (STRENGTH, "Legs")


@pytest.mark.parametrize(
    "body, minutes, focus",
    [
        ({}, 30, WorkoutFocus.ANY),  # the defaults
        ({"minutes": 45, "focus": "strength"}, 45, WorkoutFocus.STRENGTH),
        ({"minutes": 15, "focus": "mix"}, 15, WorkoutFocus.MIX),
    ],
)
def test_sends_the_chosen_length_and_focus(
    client: TestClient,
    ai_on: None,
    catalogue: dict[str, Exercise],
    claude: list[WorkoutRequest],
    body: dict,
    minutes: int,
    focus: WorkoutFocus,
) -> None:
    sign_in(client)

    client.post(URL, json=body)

    assert (claude[0].minutes, claude[0].focus) == (minutes, focus)


@pytest.mark.parametrize(
    "body", [{"minutes": 20}, {"minutes": 600}, {"focus": "yoga"}]
)
def test_choices_outside_the_menu_are_rejected(
    client: TestClient,
    ai_on: None,
    catalogue: dict[str, Exercise],
    claude: list[WorkoutRequest],
    body: dict,
) -> None:
    sign_in(client)

    assert client.post(URL, json=body).status_code == 422
    assert claude == []


def test_sends_the_last_week_of_history_oldest_first(
    client: TestClient,
    ai_on: None,
    catalogue: dict[str, Exercise],
    claude: list[WorkoutRequest],
) -> None:
    sign_in(client)
    log(client, catalogue, "Running", days_ago=7, duration_minutes=40)  # too old
    log(client, catalogue, "Running", days_ago=6, duration_minutes=30)
    log(client, catalogue, "Squat", days_ago=0, sets=3, reps=8, weight_kg=60)
    log(client, catalogue, "Walking", days_ago=-1, duration_minutes=20)  # future

    client.post(URL, json={})

    # Today plus the six days before; the load (60 kg) isn't sent at all.
    assert claude[0].history == (
        PastWorkout(6, "Running", CARDIO, None, minutes=30),
        PastWorkout(0, "Squat", STRENGTH, "Legs", sets=3, reps=8),
    )


def test_history_keeps_the_newest_entries(
    client: TestClient,
    ai_on: None,
    catalogue: dict[str, Exercise],
    claude: list[WorkoutRequest],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recommendation_service, "MAX_HISTORY_ENTRIES", 3)
    sign_in(client)
    for days_ago in range(5):
        log(client, catalogue, "Walking", days_ago=days_ago, duration_minutes=20)

    client.post(URL, json={})

    assert [w.days_ago for w in claude[0].history] == [2, 1, 0]


def test_history_is_the_users_own(
    client: TestClient,
    ai_on: None,
    catalogue: dict[str, Exercise],
    claude: list[WorkoutRequest],
) -> None:
    sign_in(client, "someone-else@example.com")
    log(client, catalogue, "Squat", sets=5, reps=5)
    sign_in(client)  # now the lifter, who has logged nothing

    client.post(URL, json={})

    assert claude[0].history == ()


def test_sends_the_profile_goal_and_activity_level(
    client: TestClient,
    ai_on: None,
    catalogue: dict[str, Exercise],
    claude: list[WorkoutRequest],
) -> None:
    sign_in(client)
    client.put("/api/profile", json=PROFILE)

    client.post(URL, json={})

    assert claude[0].goal is Goal.LOSE
    assert claude[0].activity_level is ActivityLevel.MODERATE


def test_works_without_a_profile(
    client: TestClient,
    ai_on: None,
    catalogue: dict[str, Exercise],
    claude: list[WorkoutRequest],
) -> None:
    # Unlike meal ideas (sized to calorie goals), nothing here needs one.
    sign_in(client)

    assert client.post(URL, json={}).status_code == 200
    assert (claude[0].goal, claude[0].activity_level) == (None, None)


# ------------------------------------------------------- errors and access
def test_requires_login(client: TestClient) -> None:
    assert client.post(URL, json={}).status_code == 401


def test_turned_off_returns_503_without_calling_claude(
    client: TestClient,
    catalogue: dict[str, Exercise],
    claude: list[WorkoutRequest],
) -> None:
    sign_in(client)

    response = client.post(URL, json={})

    assert response.status_code == 503
    assert "turned off" in response.json()["detail"]
    assert claude == []


def test_an_empty_catalogue_returns_503_without_using_the_allowance(
    client: TestClient,
    db: Session,
    ai_on: None,
    claude: list[WorkoutRequest],
) -> None:
    sign_in(client)  # no `catalogue` fixture: nothing seeded

    response = client.post(URL, json={})

    assert response.status_code == 503
    assert "no exercises" in response.json()["detail"]
    assert claude == []
    assert ai_requests_stored(db) == 0


def test_claude_failure_returns_503_and_still_counts(
    client: TestClient,
    db: Session,
    ai_on: None,
    catalogue: dict[str, Exercise],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A failed call may still have been billed, and the limit protects the bill.
    sign_in(client)

    def failing(request: WorkoutRequest) -> WorkoutSuggestion:
        raise AiUnavailableError("overloaded")

    monkeypatch.setattr(ai_client, "recommend_workout", failing)

    response = client.post(URL, json={})

    assert response.status_code == 503
    assert "try again" in response.json()["detail"]
    assert ai_requests_stored(db) == 1


# ---------------------------------------------------------- the allowance
def test_records_the_request_under_its_own_feature(
    client: TestClient,
    db: Session,
    ai_on: None,
    catalogue: dict[str, Exercise],
    claude: list[WorkoutRequest],
) -> None:
    sign_in(client)

    client.post(URL, json={})

    assert db.scalars(select(AiRequest.feature)).all() == ["workout_suggestions"]


def test_the_allowance_is_shared_with_the_other_ai_features(
    client: TestClient,
    db: Session,
    ai_on: None,
    catalogue: dict[str, Exercise],
    claude: list[WorkoutRequest],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ai_daily_limit", 1)
    sign_in(client)
    user = db.scalar(select(User).where(User.email == SIGNUP["email"]))
    # The day's one request already went on a photo estimate…
    ai_usage_service.check_and_record(db, user, ai_usage_service.PHOTO_ESTIMATE)

    response = client.post(URL, json={})

    # …so the workout idea is refused before reaching Claude.
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert claude == []
