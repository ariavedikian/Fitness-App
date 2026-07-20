"""Exercise routes: search the exercise catalogue."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Exercise, User
from app.schemas.workout import ExerciseRead
from app.services import exercise_service

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


@router.get(
    "/search",
    response_model=list[ExerciseRead],
    summary="Search exercises by name or muscle group",
)
def search(
    q: str = Query(min_length=1, max_length=100, description="Search text"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Exercise]:
    return exercise_service.search_exercises(db, q)
