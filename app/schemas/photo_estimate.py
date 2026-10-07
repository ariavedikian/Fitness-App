"""Pydantic schemas for photo calorie estimates."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class EstimatedItemRead(BaseModel):
    """One food Claude saw: an estimated weight plus nutrition per 100 g, so
    the client can rescale every figure when the user corrects the grams.

    Mirrors ``ai_client.EstimatedItem`` rather than reusing it — that model is
    the contract with Claude, this one the contract with the browser.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str
    grams: int
    calories_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fat_per_100g: float


class PhotoEstimateRead(BaseModel):
    """The estimate for review. ``items`` is empty when no food was seen, and
    ``note`` says what was assumed (or that there was no food)."""

    model_config = ConfigDict(from_attributes=True)

    items: list[EstimatedItemRead]
    confidence: Literal["low", "medium", "high"]
    note: str
