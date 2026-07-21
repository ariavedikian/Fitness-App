"""Tests for the WeightEntry ORM model — mainly the one-per-day constraint."""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User, WeightEntry


def _make_user(db: Session, email: str = "weigher@example.com") -> User:
    user = User(email=email, hashed_password="not-a-real-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_weight_entry_is_persisted_with_generated_fields(db: Session) -> None:
    user = _make_user(db)
    db.add(WeightEntry(user_id=user.id, date=date(2026, 7, 20), weight_kg=82.5))
    db.commit()

    saved = db.scalars(
        select(WeightEntry).where(WeightEntry.user_id == user.id)
    ).one()

    assert saved.id is not None
    assert saved.created_at is not None
    assert saved.weight_kg == 82.5


def test_one_weigh_in_per_user_per_day(db: Session) -> None:
    """The unique (user_id, date) constraint enforces the upsert model: a
    second row for the same user and day is rejected at the database."""
    user = _make_user(db)
    day = date(2026, 7, 20)
    db.add(WeightEntry(user_id=user.id, date=day, weight_kg=82.5))
    db.commit()

    db.add(WeightEntry(user_id=user.id, date=day, weight_kg=81.0))
    with pytest.raises(IntegrityError):
        db.commit()


def test_same_day_is_allowed_for_different_users(db: Session) -> None:
    """The constraint is scoped per user — two people can weigh in on the
    same date."""
    alice = _make_user(db, "alice@example.com")
    bob = _make_user(db, "bob@example.com")
    day = date(2026, 7, 20)

    db.add(WeightEntry(user_id=alice.id, date=day, weight_kg=60.0))
    db.add(WeightEntry(user_id=bob.id, date=day, weight_kg=90.0))
    db.commit()  # no IntegrityError

    assert len(db.scalars(select(WeightEntry)).all()) == 2


def test_same_user_may_weigh_in_on_different_days(db: Session) -> None:
    user = _make_user(db)
    db.add(WeightEntry(user_id=user.id, date=date(2026, 7, 20), weight_kg=82.5))
    db.add(WeightEntry(user_id=user.id, date=date(2026, 7, 21), weight_kg=82.1))
    db.commit()  # no IntegrityError

    assert len(db.scalars(select(WeightEntry)).all()) == 2
