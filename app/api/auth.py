"""Authentication routes: registration, login, logout."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.schemas.user import UserCreate, UserRead
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
