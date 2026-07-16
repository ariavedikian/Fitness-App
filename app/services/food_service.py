"""Business logic for searching the food database."""

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.models import Food

MAX_RESULTS = 20


def _escape_like(term: str) -> str:
    """Escape LIKE wildcards so a user's ``%`` or ``_`` matches literally.

    Without this, searching "100%" would translate to a pattern where ``%``
    means "any characters" and match every row in the table.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_foods(
    db: Session, query: str, limit: int = MAX_RESULTS
) -> list[Food]:
    """Find foods whose name or brand contains ``query`` (case-insensitive).

    Names that *start* with the query rank ahead of ones that merely contain
    it, so typing "ban" surfaces "Banana" above "Raw Plantain, banana-like".
    """
    term = query.strip()
    if not term:
        return []

    escaped = _escape_like(term)
    contains = f"%{escaped}%"
    starts_with = f"{escaped}%"

    stmt = (
        select(Food)
        .where(
            or_(
                Food.name.ilike(contains, escape="\\"),
                Food.brand.ilike(contains, escape="\\"),
            )
        )
        .order_by(
            # 0 sorts before 1, so prefix matches come first; then A–Z.
            case((Food.name.ilike(starts_with, escape="\\"), 0), else_=1),
            Food.name,
        )
        .limit(limit)
    )
    return list(db.scalars(stmt))
