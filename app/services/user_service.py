"""Business logic for user accounts.

This layer knows nothing about HTTP: it raises domain exceptions and lets
the API layer decide what status code they deserve.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.user import UserCreate


class EmailAlreadyRegisteredError(Exception):
    """Raised when an email is already attached to an account."""


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email)).one_or_none()


def create_user(db: Session, payload: UserCreate) -> User:
    """Create a new account, hashing the password before it is stored.

    Uniqueness is left to the database's constraint rather than a
    check-then-insert: querying first would leave a window in which two
    concurrent signups for the same email both see "available" and both
    proceed.
    """
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyRegisteredError(payload.email) from exc

    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Return the user those credentials belong to, or None."""
    user = get_by_email(db, email)

    if user is None:
        # Hash the supplied password anyway and discard the result. Without
        # this, an unknown email would answer noticeably faster than a wrong
        # password, and that timing difference alone tells an attacker which
        # emails have accounts.
        hash_password(password)
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user
