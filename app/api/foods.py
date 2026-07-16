"""Food routes: search the nutrition database."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Food, User
from app.schemas.food import FoodRead
from app.services import food_service

router = APIRouter(prefix="/api/foods", tags=["foods"])


@router.get(
    "/search",
    response_model=list[FoodRead],
    summary="Search foods by name or brand",
)
def search(
    q: str = Query(min_length=1, max_length=100, description="Search text"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Food]:
    return food_service.search_foods(db, q)
