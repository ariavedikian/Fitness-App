"""Food model: a searchable nutrition record, stored per 100 g."""

from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Food(Base):
    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(200), index=True)

    # NULL for a generic whole food (an apple); set for a packaged product.
    brand: Mapped[str | None] = mapped_column(String(200), index=True)

    # Nutrition is stored per 100 g so any logged quantity scales by a single
    # multiplication. Per-serving values are always derived, never stored, so
    # they cannot drift out of sync with these canonical numbers.
    calories_per_100g: Mapped[float] = mapped_column(Float)
    protein_per_100g: Mapped[float] = mapped_column(Float)
    carbs_per_100g: Mapped[float] = mapped_column(Float)
    fat_per_100g: Mapped[float] = mapped_column(Float)

    # One serving expressed in grams, plus a human-readable label
    # ("1 medium banana"). Lets the UI offer servings while the arithmetic
    # underneath stays gram-based.
    serving_size_g: Mapped[float] = mapped_column(Float)
    serving_label: Mapped[str] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        shown = self.name + (f" ({self.brand})" if self.brand else "")
        return f"<Food id={self.id} {shown!r}>"
