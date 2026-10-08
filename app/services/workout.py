"""Pure domain calculations for workouts.

Like ``nutrition.py``: no database, no HTTP, no clock — just the arithmetic
and the domain enum. Inputs are assumed already validated (the schema layer's
job); these functions do the math and nothing else.

Reference:
- MET (Metabolic Equivalent of Task) — a standard measure of exercise
  intensity. 1 MET is roughly the energy of sitting still; running is ~8 METs.
  The widely used approximation for energy expenditure is
  ``kcal = MET × body-weight-kg × hours``.
"""

from enum import Enum


class ExerciseType(str, Enum):
    """The two shapes a logged exercise can take.

    They need different numbers — strength is sets/reps/weight, cardio is
    duration/distance — so the type drives both validation and which metrics
    the UI shows. Stored by value ("strength") to match the JSON on the wire.
    """

    STRENGTH = "strength"
    CARDIO = "cardio"


class WorkoutFocus(str, Enum):
    """What kind of session someone wants a workout idea for.

    ``ANY`` leaves the balance to their recent history; ``MIX`` asks for both
    strength and cardio in one session.
    """

    ANY = "any"
    STRENGTH = "strength"
    CARDIO = "cardio"
    MIX = "mix"


def estimate_calories_burned(
    *, met: float, weight_kg: float, minutes: float
) -> float:
    """Estimate calories burned from an exercise's MET and how long it lasted.

    Uses the standard approximation ``kcal = MET × weight_kg × hours``. Result
    is left unrounded so callers round once at the display boundary (the same
    rule the nutrition totals follow).

    Example: 30 min of running (MET 8) at 70 kg → 8 × 70 × 0.5 = 280 kcal.
    """
    return met * weight_kg * (minutes / 60.0)
