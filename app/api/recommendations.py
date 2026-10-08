"""Recommendation routes: AI meal ideas that fit the day's remaining budget,
and workout ideas built from the exercise catalogue."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.ai_errors import rate_limited
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.recommendation import (
    MealSuggestionsRead,
    MealSuggestionsRequest,
    WorkoutIdeaRead,
    WorkoutIdeaRequest,
)
from app.services import ai_client, recommendation_service
from app.services.ai_client import AiUnavailableError
from app.services.ai_usage_service import AiRateLimitError
from app.services.recommendation_service import (
    CatalogueEmptyError,
    ProfileRequiredError,
)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


# POST, not GET: every call is billed and returns different ideas, and a GET
# can be prefetched by browsers or link previewers — spending money for a
# request nobody made.
@router.post(
    "/meals",
    response_model=MealSuggestionsRead,
    summary="Suggest meals that fit today's remaining calories and macros",
)
def suggest_meals(
    payload: MealSuggestionsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> object:
    # Checked before any other work, so a switched-off feature gives the same
    # answer whatever the user's state — and a different message from a
    # transient failure, which is worth retrying.
    if not ai_client.is_enabled():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI meal suggestions are turned off.",
        )
    try:
        return recommendation_service.suggest_meals(
            db, current_user, payload.meal_type
        )
    except ProfileRequiredError:
        # 409: the action exists but the account isn't ready for it yet.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Set up your profile to get meal suggestions.",
        )
    except AiRateLimitError as exc:
        raise rate_limited(exc)
    except AiUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Meal suggestions are unavailable right now. Please try again.",
        )


# POST for the same reason as /meals: billed, and never safe to prefetch.
@router.post(
    "/workouts",
    response_model=WorkoutIdeaRead,
    summary="Suggest a workout for today from the exercise catalogue",
)
def suggest_workout(
    payload: WorkoutIdeaRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> object:
    if not ai_client.is_enabled():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI workout ideas are turned off.",
        )
    try:
        return recommendation_service.suggest_workout(
            db, current_user, payload.minutes, payload.focus
        )
    except CatalogueEmptyError:
        # No profile is needed, so unlike /meals there's no 409: the only
        # missing prerequisite is the server's own seed data.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "There are no exercises to suggest from yet.",
        )
    except AiRateLimitError as exc:
        raise rate_limited(exc)
    except AiUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Workout ideas are unavailable right now. Please try again.",
        )
