"""Business logic for searching the food database.

Two layers of search:

* :func:`search_foods` searches only our **local** database (used on its own by
  callers that must not depend on a third party).
* :func:`search_all` is the **hybrid** search behind the API: local results
  first, then Open Food Facts, deduped and degrading gracefully when OFF is
  down. It returns the wire shape (:class:`FoodSearchResponse`) directly.
"""

from sqlalchemy import case, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Food
from app.schemas.food import FoodSearchResponse, FoodSearchResult
from app.services import off_client
from app.services.off_client import OffFood, OffUnavailableError
from app.services.search import escape_like

MAX_RESULTS = 20


class OffProductNotFoundError(Exception):
    """Raised when an ``off_id`` has no usable product on Open Food Facts."""


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

    escaped = escape_like(term)
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


def _result_from_food(food: Food) -> FoodSearchResult:
    """Map a local ``Food`` row to a search result the client logs by ``id``."""
    return FoodSearchResult(
        source="local",
        id=food.id,
        name=food.name,
        brand=food.brand,
        calories_per_100g=food.calories_per_100g,
        protein_per_100g=food.protein_per_100g,
        carbs_per_100g=food.carbs_per_100g,
        fat_per_100g=food.fat_per_100g,
        serving_size_g=food.serving_size_g,
        serving_label=food.serving_label,
    )


def _result_from_off(off: OffFood) -> FoodSearchResult:
    """Map an Open Food Facts hit to a search result the client imports first."""
    return FoodSearchResult(
        source="off",
        off_id=off.off_id,
        name=off.name,
        brand=off.brand,
        calories_per_100g=off.calories_per_100g,
        protein_per_100g=off.protein_per_100g,
        carbs_per_100g=off.carbs_per_100g,
        fat_per_100g=off.fat_per_100g,
        serving_size_g=off.serving_size_g,
        serving_label=off.serving_label,
    )


def search_all(
    db: Session, query: str, *, limit: int = MAX_RESULTS
) -> FoodSearchResponse:
    """Search local foods and Open Food Facts, merged into one ranked list.

    Local foods come first: they are curated or already-imported, and can be
    logged with no extra round-trip. Open Food Facts results follow, minus any
    product we have already imported (deduped on ``off_id``) so nothing shows
    twice. If OFF is disabled or unreachable, local results are returned anyway
    with an ``external`` status the UI can surface — a third-party outage
    degrades the feature instead of breaking search.
    """
    local = search_foods(db, query, limit=limit)
    results = [_result_from_food(food) for food in local]

    if not settings.off_enabled:
        return FoodSearchResponse(results=results, external="disabled")

    try:
        off_results = off_client.search_off(query, limit=limit)
    except OffUnavailableError:
        return FoodSearchResponse(results=results, external="unavailable")

    # Skip OFF products we have already imported locally, so a food that lives
    # in both places appears once (as the local, instantly-loggable copy).
    already_imported = {food.off_id for food in local if food.off_id}
    for off in off_results:
        if off.off_id in already_imported:
            continue
        already_imported.add(off.off_id)  # guard against dupes within OFF too
        results.append(_result_from_off(off))

    return FoodSearchResponse(results=results, external="ok")


def import_off_food(db: Session, off_id: str) -> Food:
    """Get-or-create the local ``Food`` for an Open Food Facts barcode.

    This is the "materialise on log" step: an OFF search result has no local
    ``id``, so before it can be logged we persist it once. If we have already
    imported this barcode we return the existing row without calling OFF at all
    (the fast path, and it keeps a popular food to a single fetch ever).

    Raises :class:`OffProductNotFoundError` if OFF has no usable product for
    the barcode, and propagates :class:`OffUnavailableError` if OFF is down.
    """
    off_id = off_id.strip()

    existing = db.scalar(select(Food).where(Food.off_id == off_id))
    if existing is not None:
        return existing

    # Re-fetch server-side so the persisted nutrition comes from us, not the
    # client (see FoodImportRequest / the "server owns data" decision).
    off = off_client.fetch_off_product(off_id)
    if off is None:
        raise OffProductNotFoundError(off_id)

    food = Food(
        off_id=off.off_id,
        name=off.name,
        brand=off.brand,
        calories_per_100g=off.calories_per_100g,
        protein_per_100g=off.protein_per_100g,
        carbs_per_100g=off.carbs_per_100g,
        fat_per_100g=off.fat_per_100g,
        serving_size_g=off.serving_size_g,
        serving_label=off.serving_label,
    )
    db.add(food)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request imported the same barcode first; the unique
        # off_id constraint tripped. Roll back and use the row they created.
        db.rollback()
        food = db.scalar(select(Food).where(Food.off_id == off_id))
        if food is None:  # some other integrity error — not ours to swallow
            raise
        return food

    db.refresh(food)
    return food
