"""Food routes: search the nutrition database (local + Open Food Facts)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Food, User
from app.schemas.food import FoodImportRequest, FoodRead, FoodSearchResponse
from app.services import food_service
from app.services.food_service import OffProductNotFoundError
from app.services.off_client import OffUnavailableError

router = APIRouter(prefix="/api/foods", tags=["foods"])


@router.get(
    "/search",
    response_model=FoodSearchResponse,
    summary="Search foods by name or brand (local database + Open Food Facts)",
)
def search(
    q: str = Query(min_length=1, max_length=100, description="Search text"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FoodSearchResponse:
    return food_service.search_all(db, q)


@router.post(
    "/import",
    response_model=FoodRead,
    summary="Import an Open Food Facts product so it can be logged",
)
def import_food(
    payload: FoodImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Food:
    """Materialise an OFF search result into a local food the log flow can use.

    Idempotent: importing the same barcode twice returns the same food.
    """
    try:
        return food_service.import_off_food(db, payload.off_id)
    except OffProductNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "That product could not be found on Open Food Facts.",
        )
    except OffUnavailableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Open Food Facts is currently unavailable. Please try again.",
        )
