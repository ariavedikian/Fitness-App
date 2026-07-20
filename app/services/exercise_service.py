"""Business logic for searching the exercise catalogue.

The food counterpart (``food_service``) also folds in Open Food Facts; there is
no external exercise API, so this stays a pure local search — same escaped,
prefix-ranked LIKE query, matching on the exercise name or its muscle group.
"""

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.models import Exercise
from app.services.search import escape_like

MAX_RESULTS = 20


def search_exercises(
    db: Session, query: str, limit: int = MAX_RESULTS
) -> list[Exercise]:
    """Find exercises whose name or muscle group contains ``query``.

    Names that *start* with the query rank first (typing "squ" surfaces
    "Squat" ahead of "Bulgarian Split Squat"); matching the muscle group too
    lets "legs" or "chest" pull up a whole group.
    """
    term = query.strip()
    if not term:
        return []

    escaped = escape_like(term)
    contains = f"%{escaped}%"
    starts_with = f"{escaped}%"

    stmt = (
        select(Exercise)
        .where(
            or_(
                Exercise.name.ilike(contains, escape="\\"),
                Exercise.muscle_group.ilike(contains, escape="\\"),
            )
        )
        .order_by(
            case((Exercise.name.ilike(starts_with, escape="\\"), 0), else_=1),
            Exercise.name,
        )
        .limit(limit)
    )
    return list(db.scalars(stmt))
