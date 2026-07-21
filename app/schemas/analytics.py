"""Pydantic schemas for trends & analytics."""

import datetime

from pydantic import BaseModel, ConfigDict


class DailySummaryRead(BaseModel):
    """One day's rolled-up totals, all rounded for display."""

    model_config = ConfigDict(from_attributes=True)

    date: datetime.date
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    calories_burned: int
    net_calories: int


class DailySummariesRead(BaseModel):
    """Daily totals over the requested window, oldest first.

    Echoes ``days`` back so the client knows which window it is drawing.
    Wrapped (not a bare list) to leave room for range-level summary stats later.
    """

    days: int
    entries: list[DailySummaryRead]
