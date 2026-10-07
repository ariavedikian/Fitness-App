"""HTTP responses shared by the AI routes.

Every AI feature draws on one per-user allowance, so they all answer "out of
requests" the same way.
"""

import math

from fastapi import HTTPException, status

from app.services.ai_usage_service import AiRateLimitError


def describe_wait(seconds: int) -> str:
    """A wait as a person would say it ("about 3 hours"). Rounds *up*, so
    someone who waits that long is never still blocked; the exact figure
    travels in the ``Retry-After`` header for machines."""
    minutes = math.ceil(seconds / 60)
    if minutes < 60:
        return "about a minute" if minutes == 1 else f"about {minutes} minutes"
    hours = math.ceil(seconds / 3600)
    return "about an hour" if hours == 1 else f"about {hours} hours"


def rate_limited(exc: AiRateLimitError) -> HTTPException:
    """The 429 for a user who has used their AI allowance for the window."""
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"You've used all {exc.limit} AI requests for the last 24 hours. "
        f"Try again in {describe_wait(exc.retry_after)}.",
        headers={"Retry-After": str(exc.retry_after)},
    )
