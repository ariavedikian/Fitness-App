"""Recommendation routes: AI meal ideas that fit the day's remaining budget."""

import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.recommendation import (
    MealSuggestionsRead,
    MealSuggestionsRequest,
)
from app.services import ai_client, recommendation_service
from app.services.ai_client import AiUnavailableError
from app.services.ai_usage_service import AiRateLimitError
from app.services.recommendation_service import ProfileRequiredError

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def _describe_wait(seconds: int) -> str:
    """A wait as a person would say it ("about 3 hours"). Rounds *up*, so
    someone who waits that long is never still blocked; the exact figure
    travels in the ``Retry-After`` header for machines."""
    minutes = math.ceil(seconds / 60)
    if minutes < 60:
        return "about a minute" if minutes == 1 else f"about {minutes} minutes"
    hours = math.ceil(seconds / 3600)
    return "about an hour" if hours == 1 else f"about {hours} hours"


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
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"You've used all {exc.limit} AI suggestions for the last 24 "
            f"hours. Try again in {_describe_wait(exc.retry_after)}.",
            headers={"Retry-After": str(exc.retry_after)},
        )
    except AiUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Meal suggestions are unavailable right now. Please try again.",
        )
