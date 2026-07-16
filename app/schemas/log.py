"""Pydantic schemas for meal logging."""

import datetime

from pydantic import BaseModel, Field

from app.models.log_entry import MealType

# A generous upper bound to catch fat-finger input (e.g. grams typed where
# servings were meant) without rejecting a legitimately large meal.
MAX_QUANTITY_GRAMS = 10_000


class LogEntryCreate(BaseModel):
    """Request to log a food. The server snapshots the referenced food's
    nutrition at write time — the client sends only what was eaten."""

    food_id: int
    meal_type: MealType
    quantity_grams: float = Field(gt=0, le=MAX_QUANTITY_GRAMS)
    # datetime.date, spelled out because a field named `date` would otherwise
    # shadow the type in its own annotation. Defaults to today on the server.
    date: datetime.date | None = None


class NutritionRead(BaseModel):
    """Calories and macros, rounded for display."""

    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int


class LogEntryRead(BaseModel):
    id: int
    date: datetime.date
    meal_type: MealType
    food_name: str
    brand: str | None
    quantity_grams: float
    nutrition: NutritionRead


class DayLogRead(BaseModel):
    """Everything logged on one day, plus the day's running totals."""

    date: datetime.date
    entries: list[LogEntryRead]
    totals: NutritionRead
