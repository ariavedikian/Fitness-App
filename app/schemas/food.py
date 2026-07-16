"""Pydantic schemas for foods."""

from pydantic import BaseModel, ConfigDict


class FoodRead(BaseModel):
    """A food as returned by search.

    Exposes the canonical per-100 g nutrition plus the serving metadata; the
    client derives per-serving figures for display, keeping one source of
    truth on the wire.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str | None
    calories_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fat_per_100g: float
    serving_size_g: float
    serving_label: str
