"""Pydantic schemas for body-weight tracking."""

import datetime

from pydantic import BaseModel, ConfigDict, Field

# A fat-finger guard, not a medical limit: the heaviest human on record was
# ~635 kg, so 1000 rejects nonsense without rejecting anyone real.
MAX_WEIGHT_KG = 1000


class WeightEntryCreate(BaseModel):
    """Request to record a weigh-in.

    Weight is metric (kg) on the wire — the client converts imperial input
    before sending, exactly as the profile form already does. ``date`` defaults
    to today on the server; sending a past date back-fills history.
    """

    # datetime.date, spelled out so a field named `date` doesn't shadow the
    # type in its own annotation.
    date: datetime.date | None = None
    weight_kg: float = Field(gt=0, le=MAX_WEIGHT_KG)


class WeightEntryRead(BaseModel):
    """One weigh-in.

    ``weight_kg`` is returned *unrounded*: the client rounds for display and
    needs the precision to round-trip imperial input (180 lb → 81.6466 kg →
    180 lb), unlike calories which are always whole numbers.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime.date
    weight_kg: float


class WeightHistoryRead(BaseModel):
    """A user's weigh-ins in chronological (oldest-first) order.

    Wrapped rather than returned as a bare list so summary fields (current
    weight, total change) can be added for the analytics milestone without
    breaking the response shape. Per-entry deltas are computed client-side from
    this ordered series — they are presentation math, not stored facts.
    """

    entries: list[WeightEntryRead]
