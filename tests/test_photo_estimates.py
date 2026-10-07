"""Tests for the meal-photo upload endpoint.

Claude is stubbed at the adapter boundary (``ai_client.estimate_photo``); the
vision request itself is covered by ``test_ai_client``. What's tested here is
the upload contract: what reaches Claude, what's refused before it does, and
how each outcome maps to HTTP.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AiRequest, User
from app.services import ai_client, ai_usage_service
from app.services.ai_client import (
    MAX_IMAGE_BYTES,
    AiUnavailableError,
    EstimatedItem,
    PhotoEstimate,
)

URL = "/api/photo-estimates"
SIGNUP = {"email": "snapper@example.com", "password": "correct-horse-battery"}
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

ESTIMATE = PhotoEstimate(
    items=[
        EstimatedItem(
            name="Steamed rice",
            grams=180,
            calories_per_100g=130,
            protein_per_100g=2.7,
            carbs_per_100g=28.2,
            fat_per_100g=0.3,
        )
    ],
    confidence="medium",
    note="Assumed plain rice with no butter.",
)


def sign_in(client: TestClient) -> None:
    client.post("/api/auth/register", json=SIGNUP)


def upload(
    client: TestClient,
    data: bytes = JPEG,
    content_type: str = "image/jpeg",
):
    return client.post(URL, files={"photo": ("meal.jpg", data, content_type)})


def ai_requests_stored(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AiRequest))


@pytest.fixture
def claude(monkeypatch: pytest.MonkeyPatch) -> list[tuple[bytes, str]]:
    """Stand in for Claude: record (image, media_type), answer ESTIMATE."""
    calls: list[tuple[bytes, str]] = []

    def fake_estimate(image: bytes, media_type: str) -> PhotoEstimate:
        calls.append((image, media_type))
        return ESTIMATE

    monkeypatch.setattr(ai_client, "estimate_photo", fake_estimate)
    return calls


# ---------------------------------------------------------------- success
def test_returns_the_estimate_for_review(
    client: TestClient, ai_on: None, claude: list[tuple[bytes, str]]
) -> None:
    sign_in(client)

    response = upload(client)

    assert response.status_code == 200
    assert response.json() == ESTIMATE.model_dump()
    assert claude == [(JPEG, "image/jpeg")]


def test_image_type_comes_from_the_bytes_not_the_claim(
    client: TestClient, ai_on: None, claude: list[tuple[bytes, str]]
) -> None:
    sign_in(client)

    upload(client, data=PNG, content_type="image/jpeg")  # mislabelled

    assert claude == [(PNG, "image/png")]


def test_each_estimate_is_recorded_against_the_allowance(
    client: TestClient,
    db: Session,
    ai_on: None,
    claude: list[tuple[bytes, str]],
) -> None:
    sign_in(client)

    upload(client)

    assert db.scalar(select(AiRequest.feature)) == "photo_estimate"


# ------------------------------------------------- refused before Claude
def test_rejects_a_file_that_is_not_an_image(
    client: TestClient,
    db: Session,
    ai_on: None,
    claude: list[tuple[bytes, str]],
) -> None:
    sign_in(client)

    response = upload(client, data=b"%PDF-1.7 not a photo")

    assert response.status_code == 415
    assert claude == []
    assert ai_requests_stored(db) == 0  # a bad upload costs no allowance


def test_rejects_an_oversized_photo(
    client: TestClient,
    db: Session,
    ai_on: None,
    claude: list[tuple[bytes, str]],
) -> None:
    sign_in(client)

    response = upload(client, data=JPEG + b"\x00" * MAX_IMAGE_BYTES)

    assert response.status_code == 413
    assert claude == []
    assert ai_requests_stored(db) == 0


def test_a_missing_photo_is_a_validation_error(
    client: TestClient, ai_on: None
) -> None:
    sign_in(client)
    assert client.post(URL).status_code == 422


# ------------------------------------------------------- the allowance
def test_the_allowance_is_shared_with_meal_ideas(
    client: TestClient,
    db: Session,
    ai_on: None,
    claude: list[tuple[bytes, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ai_daily_limit", 1)
    sign_in(client)
    user = db.scalar(select(User).where(User.email == SIGNUP["email"]))
    # The day's one request already went on meal ideas…
    ai_usage_service.check_and_record(db, user, ai_usage_service.MEAL_SUGGESTIONS)

    response = upload(client)

    # …so the photo is refused.
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert "AI requests" in response.json()["detail"]
    assert claude == []


# ------------------------------------------------- errors and access
def test_turned_off_returns_503(
    client: TestClient, claude: list[tuple[bytes, str]]
) -> None:
    sign_in(client)

    response = upload(client)

    assert response.status_code == 503
    assert "turned off" in response.json()["detail"]
    assert claude == []


def test_claude_failure_returns_503(
    client: TestClient, ai_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in(client)

    def failing(image: bytes, media_type: str) -> PhotoEstimate:
        raise AiUnavailableError("overloaded")

    monkeypatch.setattr(ai_client, "estimate_photo", failing)

    response = upload(client)

    assert response.status_code == 503
    assert "try again" in response.json()["detail"]


def test_requires_login(client: TestClient) -> None:
    assert upload(client).status_code == 401
