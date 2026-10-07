"""Per-user rate limiting for billed AI requests.

Every request that would reach Claude goes through :func:`check_and_record`
first: it counts the user's requests in a rolling 24-hour window and either
records this one or refuses with :class:`AiRateLimitError`. One allowance is
shared by all AI features — the point is to cap what a single account can
spend, whichever feature spends it.

Policy:

* **Only requests that would call Claude are counted.** Callers check first,
  so a spent budget, a missing profile or AI being off never get here.
* **A request counts even if the call then fails.** It is recorded *before*
  the call, because a timed-out or invalid reply may still have been billed,
  and this limit exists to protect the bill.
* **Rolling, not calendar-day.** The server's midnight isn't the user's, and
  a calendar reset would allow a double burst either side of it.

Check-and-record is one short transaction, so two simultaneous requests can
both pass only at the very edge of the limit (overshooting by one). That is
acceptable for a cost guard; an exact limit would lock the user's row.
"""

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AiRequest, User

WINDOW = timedelta(hours=24)

# Feature names recorded with each request (plain strings; see AiRequest).
MEAL_SUGGESTIONS = "meal_suggestions"
PHOTO_ESTIMATE = "photo_estimate"


class AiRateLimitError(Exception):
    """Raised when a user has used their AI allowance for the window.

    ``retry_after`` is whole seconds until a slot frees up (at least 1) — for
    the HTTP ``Retry-After`` header and a human-readable message.
    """

    def __init__(self, limit: int, retry_after: int) -> None:
        super().__init__(
            f"AI limit of {limit} per {WINDOW} reached; retry in {retry_after}s"
        )
        self.limit = limit
        self.retry_after = retry_after


def _as_utc(moment: datetime) -> datetime:
    """SQLite has no time-zone type, so it hands timestamps back naive;
    PostgreSQL returns them aware. We only ever write UTC, so a naive value
    *is* UTC — tag it so it can be compared with an aware ``now``."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def check_and_record(
    db: Session, user: User, feature: str, *, now: datetime | None = None
) -> None:
    """Record one AI request for ``user``, or raise :class:`AiRateLimitError`
    if they've reached ``settings.ai_daily_limit`` in the last 24 hours.

    ``now`` is injectable so tests can move through the window
    deterministically; it must be time-zone aware (UTC).
    """
    now = now or datetime.now(UTC)
    cutoff = now - WINDOW

    # Requests older than the window can never count again; dropping them
    # keeps the table at about one window of traffic.
    db.execute(
        delete(AiRequest).where(
            AiRequest.user_id == user.id, AiRequest.created_at <= cutoff
        )
    )
    recent = [
        _as_utc(at)
        for at in db.scalars(
            select(AiRequest.created_at)
            .where(AiRequest.user_id == user.id, AiRequest.created_at > cutoff)
            .order_by(AiRequest.created_at)
        )
    ]

    limit = settings.ai_daily_limit
    if len(recent) >= limit:
        db.commit()  # keep the pruning even though this request is refused
        # Getting back under the limit needs (count − limit + 1) requests to
        # age out; the last of those to expire sets the wait. Usually that's
        # the oldest, but the count can exceed the limit if it was lowered.
        frees_at = recent[len(recent) - limit] + WINDOW
        wait = math.ceil((frees_at - now).total_seconds())
        raise AiRateLimitError(limit, retry_after=max(1, wait))

    db.add(AiRequest(user_id=user.id, feature=feature, created_at=now))
    db.commit()
