"""Business logic for AI meal and workout suggestions.

Gathers what the server knows and asks ``ai_client`` for ideas that fit it:

* **meals** — the profile's goals and today's meals and workouts become the
  day's remaining budget. The server owns these numbers (it never trusts a
  budget sent by the client), and Claude only sees that summary.
* **workouts** — the exercise catalogue, the last week's workouts and the
  profile's goal and activity level. Claude may only pick catalogue
  exercises, and each pick is resolved back to its catalogue row, so every
  suggestion can be logged through the normal workout flow.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Exercise, MealType, User, WorkoutEntry
from app.services import (
    ai_client,
    ai_usage_service,
    log_service,
    nutrition,
    profile_service,
    workout_service,
)
from app.services.ai_client import (
    CatalogueExercise,
    MealRequest,
    MealSuggestion,
    PastWorkout,
    WorkoutRequest,
)
from app.services.workout import WorkoutFocus


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


# ---------------------------------------------------------------------------
# Workout suggestions.
# ---------------------------------------------------------------------------

# Rest is about the last day or two and balance about the last week; older
# history would only lengthen the prompt.
HISTORY_DAYS = 7

# A very busy week shouldn't balloon the prompt: keep the most recent entries.
MAX_HISTORY_ENTRIES = 40


class CatalogueEmptyError(Exception):
    """Raised when there are no exercises to suggest from (the catalogue
    hasn't been seeded) — a server setup problem, not the user's."""


@dataclass(frozen=True)
class WorkoutIdeaExercise:
    """One suggested exercise, resolved to its catalogue row so the browser
    gets the id, name and type the workout log dialog needs."""

    exercise: Exercise
    sets: int | None
    reps: int | None
    minutes: int | None
    note: str


@dataclass(frozen=True)
class WorkoutIdea:
    """A suggested session for today, made only of catalogue exercises."""

    title: str
    summary: str
    exercises: list[WorkoutIdeaExercise]


def _recent_workouts(
    db: Session, user: User, today: date
) -> tuple[PastWorkout, ...]:
    """The user's workouts from the last :data:`HISTORY_DAYS` days (today
    included), at most :data:`MAX_HISTORY_ENTRIES` of the newest, oldest
    first. Load and distance are dropped — see ``PastWorkout``."""
    since = today - timedelta(days=HISTORY_DAYS - 1)
    newest_first = db.scalars(
        select(WorkoutEntry)
        .where(
            WorkoutEntry.user_id == user.id,
            WorkoutEntry.date >= since,
            # A client may log a future date; it isn't history yet.
            WorkoutEntry.date <= today,
        )
        .order_by(
            WorkoutEntry.date.desc(),
            WorkoutEntry.created_at.desc(),
            WorkoutEntry.id.desc(),
        )
        .limit(MAX_HISTORY_ENTRIES)
    ).all()
    return tuple(
        PastWorkout(
            days_ago=(today - entry.date).days,
            name=entry.exercise_name,
            type=entry.type,
            muscle_group=entry.muscle_group,
            sets=entry.sets,
            reps=entry.reps,
            minutes=entry.duration_minutes,
        )
        for entry in reversed(newest_first)
    )


def suggest_workout(
    db: Session,
    user: User,
    minutes: int,
    focus: WorkoutFocus,
    today: date | None = None,
) -> WorkoutIdea:
    """A session for ``today`` built from the catalogue, balanced against the
    user's recent workouts.

    A profile is optional: without one, Claude simply isn't told a goal or
    activity level. Raises :class:`CatalogueEmptyError` before anything is
    counted, and lets
    :class:`~app.services.ai_usage_service.AiRateLimitError` and
    :class:`~app.services.ai_client.AiUnavailableError` propagate for the
    route to map. ``today`` is injectable for deterministic tests.
    """
    # Sorted, so the schema built from it is byte-identical between requests
    # and the API reuses its compiled grammar.
    exercises = db.scalars(
        select(Exercise).order_by(Exercise.name, Exercise.id)
    ).all()
    if not exercises:
        raise CatalogueEmptyError

    today = today or date.today()
    profile = profile_service.get_profile(db, user)
    request = WorkoutRequest(
        minutes=minutes,
        focus=focus,
        catalogue=tuple(
            CatalogueExercise(e.name, e.type, e.muscle_group) for e in exercises
        ),
        history=_recent_workouts(db, user, today),
        goal=profile.goal if profile else None,
        activity_level=profile.activity_level if profile else None,
    )

    # Counted only now, after every check that answers without calling
    # Claude (as for meal ideas).
    ai_usage_service.check_and_record(
        db, user, ai_usage_service.WORKOUT_SUGGESTIONS
    )
    suggestion = ai_client.recommend_workout(request)

    # The schema only allows catalogue names, so every name resolves.
    by_name = {e.name: e for e in exercises}
    return WorkoutIdea(
        title=suggestion.title,
        summary=suggestion.summary,
        exercises=[
            WorkoutIdeaExercise(
                exercise=by_name[item.name],
                sets=item.sets,
                reps=item.reps,
                minutes=item.minutes,
                note=item.note,
            )
            for item in suggestion.exercises
        ],
    )
