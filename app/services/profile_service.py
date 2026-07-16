"""Business logic for user profiles and their derived goals.

Bridges the stored profile to the pure nutrition math: it reads/writes rows
and converts a stored ``birth_date`` into the age those functions expect.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models import Profile, User
from app.schemas.profile import ProfileWrite
from app.services import nutrition
from app.services.nutrition import DailyGoals


def get_profile(db: Session, user: User) -> Profile | None:
    return user.profile


def upsert_profile(db: Session, user: User, payload: ProfileWrite) -> Profile:
    """Create the user's profile, or overwrite it if one already exists.

    "Upsert" (update-or-insert) matches PUT: the caller sends a complete
    profile and does not need to know or care whether it is their first time.
    """
    profile = user.profile
    if profile is None:
        profile = Profile(user_id=user.id)
        db.add(profile)

    for field, value in payload.model_dump().items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)
    return profile


def age_from_birth_date(birth_date: date, today: date | None = None) -> int:
    """Whole years between ``birth_date`` and ``today``.

    ``today`` is injectable so the calculation can be tested deterministically
    rather than depending on the real clock. The subtraction trick drops a
    year when this year's birthday has not happened yet.
    """
    today = today or date.today()
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )


def compute_goals(profile: Profile, today: date | None = None) -> DailyGoals:
    """Run the nutrition pipeline over a stored profile."""
    return nutrition.calculate_goals(
        sex=profile.sex,
        weight_kg=profile.weight_kg,
        height_cm=profile.height_cm,
        age_years=age_from_birth_date(profile.birth_date, today),
        activity_level=profile.activity_level,
        goal=profile.goal,
    )
