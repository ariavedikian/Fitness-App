"""Business logic for body-weight tracking.

A weigh-in is a plain user-owned fact — no snapshot, no catalogue. The one
wrinkle is the link back to the profile: ``Profile.weight_kg`` is the canonical
"current weight" that drives calorie/macro goals and cardio-calorie estimates,
so recording *today's* weigh-in also updates it, keeping the two from silently
diverging. Back-dated entries record history only.
"""

from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, WeightEntry
from app.schemas.weight import WeightEntryCreate


def record_weight(
    db: Session, user: User, payload: WeightEntryCreate
) -> WeightEntry:
    """Record a weigh-in, overwriting any existing entry for the same day.

    One weigh-in per day (the DB enforces it too): re-logging a date updates
    that day's weight in place rather than erroring. When the day is today, the
    profile's canonical current weight is synced so goals stay current.
    """
    day = payload.date or date_type.today()

    entry = db.scalars(
        select(WeightEntry).where(
            WeightEntry.user_id == user.id, WeightEntry.date == day
        )
    ).one_or_none()

    if entry is None:
        entry = WeightEntry(
            user_id=user.id, date=day, weight_kg=payload.weight_kg
        )
        db.add(entry)
    else:
        entry.weight_kg = payload.weight_kg

    # Logging *today's* weight is a statement about "current weight", so keep
    # the profile (which drives goals + cardio calories) in step. Back-dated
    # entries are history only. No profile yet? Nothing to sync — degrade
    # quietly, the same stance workout estimation takes.
    if day == date_type.today() and user.profile is not None:
        user.profile.weight_kg = payload.weight_kg

    db.commit()
    db.refresh(entry)
    return entry


def get_entries(db: Session, user: User) -> list[WeightEntry]:
    """All of the user's weigh-ins, oldest first — the natural series order for
    computing deltas and (next milestone) charting a trend."""
    stmt = (
        select(WeightEntry)
        .where(WeightEntry.user_id == user.id)
        .order_by(WeightEntry.date)
    )
    return list(db.scalars(stmt))


def delete_entry(db: Session, user: User, entry_id: int) -> bool:
    """Delete one of the user's own weigh-ins. Returns False if it is missing or
    belongs to someone else, so the endpoint can 404 without ever confirming
    another user's entry exists.

    The profile's current weight is deliberately left untouched: it records the
    last weight the user stated, and there is no correct value to revert it to.
    """
    entry = db.get(WeightEntry, entry_id)
    if entry is None or entry.user_id != user.id:
        return False

    db.delete(entry)
    db.commit()
    return True
