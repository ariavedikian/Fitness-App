"""Tests for the per-user AI rate limit (a rolling 24-hour window).

Time is injected (``now=``) so the window can be walked deterministically.
These run on SQLite, which returns timestamps without a time zone, so they
also cover the naive-means-UTC handling in ``_as_utc``.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AiRequest, User
from app.services import ai_usage_service
from app.services.ai_usage_service import MEAL_SUGGESTIONS, AiRateLimitError

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


@pytest.fixture
def limit_of_3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ai_daily_limit", 3)


def make_user(db: Session, email: str = "cook@example.com") -> User:
    user = User(email=email, hashed_password="not-a-real-hash")
    db.add(user)
    db.commit()
    return user


def record(db: Session, user: User, at: datetime) -> None:
    ai_usage_service.check_and_record(db, user, MEAL_SUGGESTIONS, now=at)


def stored(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AiRequest))


def test_records_each_request(db: Session, limit_of_3: None) -> None:
    user = make_user(db)

    record(db, user, NOW)

    row = db.scalars(select(AiRequest)).one()
    assert (row.user_id, row.feature) == (user.id, "meal_suggestions")


def test_allows_up_to_the_limit_then_refuses(
    db: Session, limit_of_3: None
) -> None:
    user = make_user(db)
    for minute in range(3):
        record(db, user, NOW + timedelta(minutes=minute))

    with pytest.raises(AiRateLimitError) as refused:
        record(db, user, NOW + timedelta(minutes=10))

    assert refused.value.limit == 3
    # The oldest request (at NOW) frees its slot at NOW + 24 h, which is
    # 23 h 50 min after this attempt at NOW + 10 min.
    assert refused.value.retry_after == (23 * 60 + 50) * 60
    assert stored(db) == 3  # a refused request is not recorded


def test_a_request_counts_for_exactly_24_hours(
    db: Session, limit_of_3: None
) -> None:
    user = make_user(db)
    for minute in range(3):
        record(db, user, NOW + timedelta(minutes=minute))

    # At NOW + 24 h the first request has aged out, freeing one slot.
    record(db, user, NOW + timedelta(hours=24))

    # The expired row was pruned, so the table holds just the window.
    assert stored(db) == 3


def test_the_limit_is_per_user(db: Session, limit_of_3: None) -> None:
    alice = make_user(db, "alice@example.com")
    bob = make_user(db, "bob@example.com")
    for minute in range(3):
        record(db, alice, NOW + timedelta(minutes=minute))

    record(db, bob, NOW + timedelta(minutes=5))  # unaffected by Alice's use

    with pytest.raises(AiRateLimitError):
        record(db, alice, NOW + timedelta(minutes=5))


def test_wait_when_already_over_a_lowered_limit(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ai_daily_limit", 4)
    user = make_user(db)
    for hour in range(4):
        record(db, user, NOW + timedelta(hours=hour))
    monkeypatch.setattr(settings, "ai_daily_limit", 2)

    with pytest.raises(AiRateLimitError) as refused:
        record(db, user, NOW + timedelta(hours=5))

    # 4 recorded, limit 2: three must age out to get under it. The third
    # (NOW + 2 h) expires at NOW + 26 h — 21 h after this attempt.
    assert refused.value.retry_after == 21 * 3600
