"""Photo estimate routes: upload a meal photo, get back a nutrition estimate."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.ai_errors import rate_limited
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.photo_estimate import PhotoEstimateRead
from app.services import ai_client, photo_estimate_service
from app.services.ai_client import AiUnavailableError
from app.services.ai_usage_service import AiRateLimitError
from app.services.photo_estimate_service import (
    ImageTooLargeError,
    UnsupportedImageError,
)

router = APIRouter(prefix="/api/photo-estimates", tags=["photo estimates"])


@router.post(
    "",
    response_model=PhotoEstimateRead,
    summary="Estimate the food in a meal photo",
)
def create_photo_estimate(
    photo: UploadFile = File(description="A JPEG, PNG, GIF or WebP photo"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> object:
    if not ai_client.is_enabled():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI photo estimates are turned off.",
        )

    # Read at most one byte past the limit: enough to tell "too large" without
    # pulling an arbitrarily big upload into memory. (A hard cap on request
    # size belongs at the reverse proxy in production.)
    image = photo.file.read(ai_client.MAX_IMAGE_BYTES + 1)
    try:
        return photo_estimate_service.estimate(db, current_user, image)
    except ImageTooLargeError:
        limit_mb = ai_client.MAX_IMAGE_BYTES // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"That photo is too large (the limit is {limit_mb} MB).",
        )
    except UnsupportedImageError:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Please upload a JPEG, PNG, GIF or WebP photo.",
        )
    except AiRateLimitError as exc:
        raise rate_limited(exc)
    except AiUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Photo estimates are unavailable right now. Please try again.",
        )
