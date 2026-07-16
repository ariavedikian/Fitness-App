"""Pydantic schemas for the profile and its derived goals.

This is the validation boundary: the nutrition calculations assume sane
numbers, and this is where that assumption is enforced before any value
reaches them.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.nutrition import ActivityLevel, Goal, Sex

# Minimum sign-up age. Many jurisdictions treat under-13 personal data
# specially (e.g. COPPA in the US); refusing it here keeps that data out
# of the system entirely.
MIN_AGE_YEARS = 13
MAX_AGE_YEARS = 120


class ProfileWrite(BaseModel):
    """The full profile a client sends to create or replace their stats.

    PUT semantics: every field is required because the request represents the
    complete, current profile rather than a patch of changed fields.
    """

    # Bounds are generous sanity limits, not medical judgements — they exist
    # to reject fat-finger input (a height of 18 cm, a weight of 7000 kg),
    # which would otherwise produce absurd but valid-looking goals.
    height_cm: float = Field(gt=0, le=300)
    weight_kg: float = Field(gt=0, le=700)
    birth_date: date
    sex: Sex
    activity_level: ActivityLevel
    goal: Goal

    @field_validator("birth_date")
    @classmethod
    def birth_date_must_be_realistic(cls, value: date) -> date:
        today = date.today()
        if value >= today:
            raise ValueError("birth date must be in the past")

        age = today.year - value.year - (
            (today.month, today.day) < (value.month, value.day)
        )
        if age < MIN_AGE_YEARS:
            raise ValueError(f"you must be at least {MIN_AGE_YEARS} years old")
        if age > MAX_AGE_YEARS:
            raise ValueError("birth date is unrealistically far in the past")
        return value


class ProfileRead(BaseModel):
    """A stored profile as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    height_cm: float
    weight_kg: float
    birth_date: date
    sex: Sex
    activity_level: ActivityLevel
    goal: Goal
    updated_at: datetime


class MacrosRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    protein_g: int
    carbs_g: int
    fat_g: int


class GoalsRead(BaseModel):
    """Computed daily targets. Not stored anywhere — derived on request from
    the profile, so they are always current with the latest stats."""

    model_config = ConfigDict(from_attributes=True)

    bmr: int
    tdee: int
    calories: int
    macros: MacrosRead
