"""Shared FastAPI dependencies.

``get_current_user`` is the gate every authenticated endpoint goes through:
declaring it as a dependency is what makes a route private.
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


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the signed-in user, or reject the request with 401."""
    user_id = request.session.get(SESSION_USER_ID_KEY)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )

    user = user_service.get_by_id(db, user_id)
    if user is None:
        # A validly signed cookie for an account that no longer exists.
        # Drop the session rather than leaving the client in a state where
        # every request fails.
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )

    return user
