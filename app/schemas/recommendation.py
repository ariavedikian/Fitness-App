"""Pydantic schemas for AI meal suggestions."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.log_entry import MealType


class MealSuggestionsRequest(BaseModel):
    """Ask for meal ideas. Only the meal is chosen by the client — the budget
    is computed server-side from the profile and today's log, and the number
    of ideas is fixed, so a client can't inflate the cost of a call.

    The browser sends ``meal_type`` (from its own time of day) because the
    server's clock isn't in the user's timezone; ``null`` means any meal.
    """

    meal_type: MealType | None = None


class MealSuggestionRead(BaseModel):
    """One meal idea with estimated nutrition (whole numbers — estimates).

    Mirrors ``ai_client.MealSuggestion`` deliberately rather than reusing it:
    that model is the contract with Claude, this one the contract with the
    browser, so a field added for Claude can't leak into the API unnoticed.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int


class MealSuggestionsRead(BaseModel):
    """``ok`` with ideas, or ``budget_spent`` (nothing left today, no ideas
    fetched) — a normal answer the UI shows as a message, not an error."""

    model_config = ConfigDict(from_attributes=True)

    status: Literal["ok", "budget_spent"]
    suggestions: list[MealSuggestionRead]
