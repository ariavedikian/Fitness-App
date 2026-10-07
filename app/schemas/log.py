"""Pydantic schemas for meal logging."""

import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.log_entry import MealType

# A generous upper bound to catch fat-finger input (e.g. grams typed where
# servings were meant) without rejecting a legitimately large meal.
MAX_QUANTITY_GRAMS = 10_000

# Pure fat is 900 kcal/100 g — the physical ceiling for any real food.
MAX_KCAL_PER_100G = 900


class LogEntryCreate(BaseModel):
    """Request to log a food. The server snapshots the referenced food's
    nutrition at write time — the client sends only what was eaten."""

    food_id: int
    meal_type: MealType
    quantity_grams: float = Field(gt=0, le=MAX_QUANTITY_GRAMS)
    # datetime.date, spelled out because a field named `date` would otherwise
    # shadow the type in its own annotation. Defaults to today on the server.
    date: datetime.date | None = None


class CustomFoodItem(BaseModel):
    """A food that isn't in the catalogue, with its nutrition supplied by the
    client (today: a photo estimate the user reviewed). The server can't
    verify where these numbers came from, so it bounds them physically."""

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    quantity_grams: float = Field(gt=0, le=MAX_QUANTITY_GRAMS)
    calories_per_100g: float = Field(ge=0, le=MAX_KCAL_PER_100G)
    protein_per_100g: float = Field(ge=0, le=100)
    carbs_per_100g: float = Field(ge=0, le=100)
    fat_per_100g: float = Field(ge=0, le=100)


class CustomLogCreate(BaseModel):
    """Log one or more custom foods to a meal, all or nothing."""

    meal_type: MealType
    date: datetime.date | None = None  # defaults to today on the server
    # A plate's worth, not a bulk import.
    items: list[CustomFoodItem] = Field(min_length=1, max_length=20)


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
