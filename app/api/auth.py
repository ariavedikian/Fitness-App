"""Authentication routes: registration, login, logout."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import SESSION_USER_ID_KEY, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.user import UserCreate, UserLogin, UserRead
from app.services import user_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    try:
        return user_service.create_user(db, payload)
    except user_service.EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        ) from exc


@router.post(
    "/login",
    response_model=UserRead,
    summary="Sign in and start a session",
)
def login(
    payload: UserLogin, request: Request, db: Session = Depends(get_db)
) -> User:
    user = user_service.authenticate(db, payload.email, payload.password)

    if user is None:
        # One message for both "no such email" and "wrong password": naming
        # which one failed would confirm to an attacker that an account
        # exists before they have any valid credentials.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    # Start from an empty session so nothing from the anonymous visit
    # carries into the authenticated one.
    request.session.clear()
    request.session[SESSION_USER_ID_KEY] = user.id

    return user


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End the current session",
)
def logout(request: Request) -> None:
    request.session.clear()


@router.get(
    "/me",
    response_model=UserRead,
    summary="Return the signed-in user",
)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
