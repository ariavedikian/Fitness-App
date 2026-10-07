"""Business logic for meal logging."""

from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Food, LogEntry, User
from app.schemas.log import CustomLogCreate, LogEntryCreate
from app.services import nutrition
from app.services.nutrition import Nutrition


class FoodNotFoundError(Exception):
    """Raised when logging references a food that does not exist."""


def create_entry(db: Session, user: User, payload: LogEntryCreate) -> LogEntry:
    """Log a food, copying its nutrition into the entry (the snapshot)."""
    food = db.get(Food, payload.food_id)
    if food is None:
        raise FoodNotFoundError(payload.food_id)

    entry = LogEntry(
        user_id=user.id,
        food_id=food.id,
        date=payload.date or date_type.today(),
        meal_type=payload.meal_type,
        quantity_grams=payload.quantity_grams,
        # Snapshot: these are copied now and never read back from `food`.
        food_name=food.name,
        brand=food.brand,
        calories_per_100g=food.calories_per_100g,
        protein_per_100g=food.protein_per_100g,
        carbs_per_100g=food.carbs_per_100g,
        fat_per_100g=food.fat_per_100g,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def create_custom_entries(
    db: Session, user: User, payload: CustomLogCreate
) -> list[LogEntry]:
    """Log foods that aren't in the catalogue, nutrition supplied by the
    client — e.g. a reviewed photo estimate.

    Each item becomes an ordinary snapshot entry with no food behind it
    (``food_id`` is NULL), so it reads, totals and deletes exactly like any
    other. Nothing is added to the shared food catalogue: one person's
    estimate isn't a food everyone should find in search. All the items are
    committed together, so a meal is never half-logged.
    """
    day = payload.date or date_type.today()
    entries = [
        LogEntry(
            user_id=user.id,
            food_id=None,
            date=day,
            meal_type=payload.meal_type,
            quantity_grams=item.quantity_grams,
            food_name=item.name,
            brand=None,
            calories_per_100g=item.calories_per_100g,
            protein_per_100g=item.protein_per_100g,
            carbs_per_100g=item.carbs_per_100g,
            fat_per_100g=item.fat_per_100g,
        )
        for item in payload.items
    ]
    db.add_all(entries)
    db.commit()
    for entry in entries:
        db.refresh(entry)
    return entries


def get_day_entries(db: Session, user: User, day: date_type) -> list[LogEntry]:
    stmt = (
        select(LogEntry)
        .where(LogEntry.user_id == user.id, LogEntry.date == day)
        .order_by(LogEntry.created_at, LogEntry.id)
    )
    return list(db.scalars(stmt))


def delete_entry(db: Session, user: User, entry_id: int) -> bool:
    """Delete one of the user's own entries. Returns False if it is missing
    or belongs to someone else — the caller turns both into a 404 so the
    endpoint never confirms another user's entry exists."""
    entry = db.get(LogEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        return False

    db.delete(entry)
    db.commit()
    return True


def entry_nutrition(entry: LogEntry) -> Nutrition:
    """Scale a logged entry's snapshot to the amount actually eaten."""
    return nutrition.scale_per_100g(
        calories_per_100g=entry.calories_per_100g,
        protein_per_100g=entry.protein_per_100g,
        carbs_per_100g=entry.carbs_per_100g,
        fat_per_100g=entry.fat_per_100g,
        grams=entry.quantity_grams,
    )


def day_totals(entries: list[LogEntry]) -> Nutrition:
    """Sum the nutrition of every entry, unrounded, for one rounding at the end."""
    return sum((entry_nutrition(e) for e in entries), Nutrition())
