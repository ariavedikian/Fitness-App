"""Analytics routes: daily aggregates for trend charts."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.analytics import DailySummariesRead, DailySummaryRead
from app.services import analytics_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# A year is plenty of history for a portfolio app and caps the work per request.
MAX_DAYS = 365
DEFAULT_DAYS = 30


@router.get(
    "/daily",
    response_model=DailySummariesRead,
    summary="Daily calorie & macro totals over a window",
)
def read_daily(
    days: int = Query(default=DEFAULT_DAYS, ge=1, le=MAX_DAYS),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailySummariesRead:
    summaries = analytics_service.daily_summaries(db, current_user, days)
    return DailySummariesRead(
        days=days,
        entries=[DailySummaryRead.model_validate(s) for s in summaries],
    )
