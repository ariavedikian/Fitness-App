"""Business logic for photo calorie estimates.

Checks an uploaded image, counts it against the user's AI allowance, and asks
``ai_client`` for an estimate. Nothing is stored: the image lives only in this
request's memory, and the estimate goes back to the browser for the user to
review. Logging is a separate, explicit step (``POST /api/log/custom``).

The checks run cheapest-first, so an upload that can't succeed never uses up
any of the allowance.
"""

from sqlalchemy.orm import Session

from app.models import User
from app.services import ai_client, ai_usage_service
from app.services.ai_client import PhotoEstimate


class ImageTooLargeError(Exception):
    """The upload is bigger than ``ai_client.MAX_IMAGE_BYTES``."""


class UnsupportedImageError(Exception):
    """The upload isn't an image format Claude can read, judged by its bytes
    (not by the client's claimed content type)."""


def estimate(db: Session, user: User, image: bytes) -> PhotoEstimate:
    """Estimate the food in ``image`` for ``user``.

    Raises :class:`ImageTooLargeError` or :class:`UnsupportedImageError` for
    an unusable upload, and lets ``AiRateLimitError`` and
    ``AiUnavailableError`` propagate for the route to map.
    """
    if len(image) > ai_client.MAX_IMAGE_BYTES:
        raise ImageTooLargeError
    media_type = ai_client.sniff_image_type(image)
    if media_type is None:
        raise UnsupportedImageError

    # Counted only once the upload has proven usable.
    ai_usage_service.check_and_record(db, user, ai_usage_service.PHOTO_ESTIMATE)
    return ai_client.estimate_photo(image, media_type)
