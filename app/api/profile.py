"""Profile routes: read and set body stats, and read derived goals."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.profile import GoalsRead, ProfileRead, ProfileWrite
from app.services import profile_service

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("", response_model=ProfileRead, summary="Get the current profile")
def read_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> object:
    profile = profile_service.get_profile(db, current_user)
    if profile is None:
        # 404 because the profile sub-resource genuinely does not exist yet;
        # the frontend reads this as "show the empty setup form".
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile yet.",
        )
    return profile


@router.put("", response_model=ProfileRead, summary="Create or replace profile")
def write_profile(
    payload: ProfileWrite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> object:
    return profile_service.upsert_profile(db, current_user, payload)


@router.get(
    "/goals",
    response_model=GoalsRead,
    summary="Get daily calorie and macro goals",
)
def read_goals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> object:
    profile = profile_service.get_profile(db, current_user)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Set up your profile to see your goals.",
        )
    return profile_service.compute_goals(profile)
