"""Meal log routes: add entries, read a day, delete an entry."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import LogEntry, User
from app.schemas.log import DayLogRead, LogEntryCreate, LogEntryRead, NutritionRead
from app.services import log_service
from app.services.nutrition import Nutrition

router = APIRouter(prefix="/api/log", tags=["log"])


def _nutrition_read(n: Nutrition) -> NutritionRead:
    # Round only here, at the display boundary — never mid-calculation.
    return NutritionRead(
        calories=round(n.calories),
        protein_g=round(n.protein_g),
        carbs_g=round(n.carbs_g),
        fat_g=round(n.fat_g),
    )


def _entry_read(entry: LogEntry) -> LogEntryRead:
    return LogEntryRead(
        id=entry.id,
        date=entry.date,
        meal_type=entry.meal_type,
        food_name=entry.food_name,
        brand=entry.brand,
        quantity_grams=entry.quantity_grams,
        nutrition=_nutrition_read(log_service.entry_nutrition(entry)),
    )


@router.post(
    "",
    response_model=LogEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log a food",
)
def create_log_entry(
    payload: LogEntryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LogEntryRead:
    try:
        entry = log_service.create_entry(db, current_user, payload)
    except log_service.FoodNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Food not found."
        ) from exc
    return _entry_read(entry)


@router.get("", response_model=DayLogRead, summary="Read a day's log")
def read_day(
    day: date | None = Query(default=None, alias="date"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DayLogRead:
    day = day or date.today()
    entries = log_service.get_day_entries(db, current_user, day)
    return DayLogRead(
        date=day,
        entries=[_entry_read(e) for e in entries],
        totals=_nutrition_read(log_service.day_totals(entries)),
    )


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a log entry",
)
def delete_log_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not log_service.delete_entry(db, current_user, entry_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Log entry not found."
        )
