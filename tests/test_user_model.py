"""Tests for the User ORM model."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User


def test_user_is_persisted_with_generated_fields(db: Session) -> None:
    db.add(User(email="lifter@example.com", hashed_password="not-a-real-hash"))
    db.commit()

    saved = db.scalars(select(User).where(User.email == "lifter@example.com")).one()

    assert saved.id is not None
    assert saved.created_at is not None


def test_email_must_be_unique(db: Session) -> None:
    db.add(User(email="dupe@example.com", hashed_password="hash-one"))
    db.commit()

    db.add(User(email="dupe@example.com", hashed_password="hash-two"))

    with pytest.raises(IntegrityError):
        db.commit()
