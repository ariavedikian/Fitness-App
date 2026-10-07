"""Business logic for AI meal suggestions.

Gathers what the server knows — the profile's goals, today's meals and
workouts — into the day's remaining budget, then asks ``ai_client`` for ideas
that fit it. The server owns these numbers (it never trusts a budget sent by
the client), and Claude only ever sees that summary, never the raw log.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from sqlalchemy.orm import Session

from app.models import MealType, User
from app.services import (
    ai_client,
    ai_usage_service,
    log_service,
    nutrition,
    profile_service,
    workout_service,
)
from app.services.ai_client import MealRequest, MealSuggestion


class ProfileRequiredError(Exception):
    """Raised when the user has no profile: suggestions are sized to daily
    goals, and goals are derived from the profile."""


# Below roughly a small snack (an apple is ~95 kcal) there's nothing useful
# left to suggest, so we say the budget is spent rather than pay for a call
# whose best answer is "black coffee".
MIN_CALORIES_TO_SUGGEST = 100


@dataclass(frozen=True)
class MealSuggestions:
    """The outcome of a suggestion request.

    ``budget_spent`` is a normal answer, not an error: the user simply has
    (almost) nothing left today, so no ideas are fetched.
    """

    status: Literal["ok", "budget_spent"]
    suggestions: list[MealSuggestion] = field(default_factory=list)


def suggest_meals(
    db: Session,
    user: User,
    meal_type: MealType | None,
    today: date | None = None,
) -> MealSuggestions:
    """Meal ideas that fit what's left of ``user``'s budget for ``today``.

    Raises :class:`ProfileRequiredError` without a profile, and lets
    :class:`~app.services.ai_usage_service.AiRateLimitError` and
    :class:`~app.services.ai_client.AiUnavailableError` propagate for the
    route to map. ``today`` is injectable for deterministic tests.
    """
    profile = profile_service.get_profile(db, user)
    if profile is None:
        raise ProfileRequiredError

    today = today or date.today()
    goals = profile_service.compute_goals(profile, today)
    eaten = log_service.day_totals(log_service.get_day_entries(db, user, today))
    burned = workout_service.day_total_calories(
        workout_service.get_day_entries(db, user, today)
    )
    remaining = nutrition.remaining_budget(goals, eaten, burned)

    if remaining.calories < MIN_CALORIES_TO_SUGGEST:
        return MealSuggestions(status="budget_spent")

    # Counted only now, after every check that answers without calling
    # Claude, so a spent budget never uses up the allowance. Raises
    # AiRateLimitError when the user is out of requests for the window.
    ai_usage_service.check_and_record(
        db, user, ai_usage_service.MEAL_SUGGESTIONS
    )
    request = MealRequest(remaining=remaining, meal_type=meal_type)
    return MealSuggestions(
        status="ok", suggestions=ai_client.recommend_meals(request)
    )
