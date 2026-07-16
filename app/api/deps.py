"""Shared FastAPI dependencies.

Two ways to ask about the session, because the two surfaces want different
answers to "nobody is signed in": an API route should say 401, while a page
should send the visitor to the login screen.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.services import user_service

# The only thing we put in the session cookie. Everything else about the
# user is looked up fresh from the database on each request, so a cookie
# issued yesterday cannot carry stale data.
SESSION_USER_ID_KEY = "user_id"


def get_optional_user(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    """Resolve the signed-in user, or None if the visitor is anonymous."""
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if user_id is None:
        return None

    user = user_service.get_by_id(db, user_id)
    if user is None:
        # A validly signed cookie for an account that no longer exists.
        # Drop the session rather than leaving the client in a state where
        # every request fails.
        request.session.clear()
        return None

    return user


def get_current_user(
    user: User | None = Depends(get_optional_user),
) -> User:
    """Require a signed-in user. Declaring this makes an API route private."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    return user
