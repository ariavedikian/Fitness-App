"""Business logic for trends & analytics: daily aggregates over a date range.

Rolls the meal log and workout log up into one row per day so the frontend can
plot calorie and macro trends. Reuses ``log_service.day_totals`` for the
nutrition math, so a day here sums exactly the way the diary and dashboard do
(unrounded, rounded once at the end).

A day appears only if it has at least one *meal* entry: a day with no food
logged means "not tracked", not "ate nothing", and zero-filling it would drag
the calorie line to the floor and lie about the trend. Workout calories are
folded into the days that are present.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date as date_type, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LogEntry, User, WorkoutEntry
from app.services import log_service


@dataclass(frozen=True)
class DailySummary:
    """One day's totals. Every figure is rounded for display; ``net_calories``
    is eaten minus burned (the same net the dashboard shows), rounded once."""

    date: date_type
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    calories_burned: int
    net_calories: int


def daily_summaries(
    db: Session, user: User, days: int
) -> list[DailySummary]:
    """The user's per-day totals for the last ``days`` days, oldest first.

    Only days with meal entries are returned (see module docstring); the series
    is therefore sparse, which the chart draws as a connected line.
    """
    end = date_type.today()
    start = end - timedelta(days=days - 1)

    # Meal entries grouped by day.
    log_stmt = select(LogEntry).where(
        LogEntry.user_id == user.id,
        LogEntry.date >= start,
        LogEntry.date <= end,
    )
    logs_by_day: dict[date_type, list[LogEntry]] = defaultdict(list)
    for entry in db.scalars(log_stmt):
        logs_by_day[entry.date].append(entry)

    # Workout calories burned, summed per day over the same window.
    workout_stmt = select(WorkoutEntry).where(
        WorkoutEntry.user_id == user.id,
        WorkoutEntry.date >= start,
        WorkoutEntry.date <= end,
    )
    burned_by_day: dict[date_type, float] = defaultdict(float)
    for w in db.scalars(workout_stmt):
        burned_by_day[w.date] += w.calories_burned or 0.0

    summaries: list[DailySummary] = []
    for day in sorted(logs_by_day):
        totals = log_service.day_totals(logs_by_day[day])
        burned = burned_by_day.get(day, 0.0)
        summaries.append(
            DailySummary(
                date=day,
                calories=round(totals.calories),
                protein_g=round(totals.protein_g),
                carbs_g=round(totals.carbs_g),
                fat_g=round(totals.fat_g),
                calories_burned=round(burned),
                # Round once from the unrounded values, like the dashboard.
                net_calories=round(totals.calories - burned),
            )
        )
    return summaries
