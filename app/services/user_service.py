"""Business logic for user accounts.

This layer knows nothing about HTTP: it raises domain exceptions and lets
the API layer decide what status code they deserve.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import User
from app.schemas.user import UserCreate


class EmailAlreadyRegisteredError(Exception):
    """Raised when an email is already attached to an account."""


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
