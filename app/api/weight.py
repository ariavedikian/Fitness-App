"""Body-weight routes: record a weigh-in, read history, delete an entry."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.weight import (
    WeightEntryCreate,
    WeightEntryRead,
    WeightHistoryRead,
)
from app.services import weight_service

router = APIRouter(prefix="/api/weight", tags=["weight"])


@router.post(
    "",
    response_model=WeightEntryRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a weigh-in",
)
def record_weight(
    payload: WeightEntryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeightEntryRead:
    # Upsert: re-logging a day overwrites it, so this may update rather than
    # create. 201 is close enough and the client just re-reads the history.
    entry = weight_service.record_weight(db, current_user, payload)
    return WeightEntryRead.model_validate(entry)


@router.get("", response_model=WeightHistoryRead, summary="Read weight history")
def read_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeightHistoryRead:
    entries = weight_service.get_entries(db, current_user)
    return WeightHistoryRead(
        entries=[WeightEntryRead.model_validate(e) for e in entries]
    )


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a weigh-in",
)
def delete_weight_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not weight_service.delete_entry(db, current_user, entry_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weight entry not found.",
        )
