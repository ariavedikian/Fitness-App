"""Pure domain calculations for daily energy and macronutrient goals.

No database, no HTTP, no clock — just the arithmetic that turns a person's
body stats into daily targets. That purity is the point: every function here
is a plain input-to-output mapping, so it can be tested without any setup and
reused from a service, a script, or a test without dragging dependencies
along.

Inputs are assumed already validated (that is the schema layer's job); these
functions do the math and nothing else.

References:
- Mifflin-St Jeor equation (1990) — the modern standard for estimating
  resting metabolic rate, more accurate than the older Harris-Benedict.
- Atwater factors — energy per gram of each macronutrient.
"""

from dataclasses import dataclass
from enum import Enum


class Sex(str, Enum):
    """Biological sex.

    Required because the Mifflin-St Jeor equation uses a different constant
    for each; it is an input to the metabolic formula, not a profile
    identity field.
    """

    MALE = "male"
    FEMALE = "female"


class ActivityLevel(str, Enum):
    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"


class Goal(str, Enum):
    LOSE = "lose"
    MAINTAIN = "maintain"
    GAIN = "gain"


# Multiplier applied to BMR to account for daily movement (the standard
# activity factors that pair with Mifflin-St Jeor).
_ACTIVITY_MULTIPLIERS: dict[ActivityLevel, float] = {
    ActivityLevel.SEDENTARY: 1.2,
    ActivityLevel.LIGHT: 1.375,
    ActivityLevel.MODERATE: 1.55,
    ActivityLevel.ACTIVE: 1.725,
    ActivityLevel.VERY_ACTIVE: 1.9,
}

# Daily calorie adjustment from maintenance for each goal. 500 kcal/day is
# the textbook deficit/surplus for roughly 0.45 kg (1 lb) per week.
_GOAL_ADJUSTMENTS: dict[Goal, int] = {
    Goal.LOSE: -500,
    Goal.MAINTAIN: 0,
    Goal.GAIN: 500,
}

# Energy per gram of each macronutrient (kcal/g).
CALORIES_PER_GRAM: dict[str, int] = {"protein": 4, "carbs": 4, "fat": 9}


@dataclass(frozen=True)
class MacroSplit:
    """The fraction of total calories from each macronutrient.

    Frozen so a split cannot be mutated after construction, and validated so
    an impossible split (fractions that do not add up to a whole) fails loudly
    at creation rather than silently skewing every downstream number.
    """

    protein: float
    carbs: float
    fat: float

    def __post_init__(self) -> None:
        total = self.protein + self.carbs + self.fat
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"macro split must sum to 1.0, got {total:.3f}"
            )


# A balanced, protein-forward default. Deliberately a module constant so the
# app has one obvious place to change its default macro strategy.
DEFAULT_MACRO_SPLIT = MacroSplit(protein=0.30, carbs=0.40, fat=0.30)


@dataclass(frozen=True)
class Macros:
    protein_g: int
    carbs_g: int
    fat_g: int


@dataclass(frozen=True)
class DailyGoals:
    """The full set of daily targets derived from a person's stats."""

    bmr: int
    tdee: int
    calories: int
    macros: Macros


def calculate_bmr(
    *, sex: Sex, weight_kg: float, height_cm: float, age_years: int
) -> float:
    """Basal metabolic rate in kcal/day, via Mifflin-St Jeor.

    BMR is the energy the body burns at complete rest — the floor before any
    activity is added.
    """
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age_years
    sex_offset = 5 if sex is Sex.MALE else -161
    return base + sex_offset


def calculate_tdee(bmr: float, activity_level: ActivityLevel) -> float:
    """Total daily energy expenditure: BMR scaled for activity (kcal/day).

    This is maintenance — eat this much and weight holds steady.
    """
    return bmr * _ACTIVITY_MULTIPLIERS[activity_level]


def calculate_calorie_goal(tdee: float, goal: Goal) -> int:
    """Daily calorie target for a weight goal, rounded to a whole calorie."""
    return round(tdee + _GOAL_ADJUSTMENTS[goal])


def calculate_macros(
    calories: int, split: MacroSplit = DEFAULT_MACRO_SPLIT
) -> Macros:
    """Split a calorie target into grams of protein, carbs, and fat."""
    return Macros(
        protein_g=round(calories * split.protein / CALORIES_PER_GRAM["protein"]),
        carbs_g=round(calories * split.carbs / CALORIES_PER_GRAM["carbs"]),
        fat_g=round(calories * split.fat / CALORIES_PER_GRAM["fat"]),
    )


def calculate_goals(
    *,
    sex: Sex,
    weight_kg: float,
    height_cm: float,
    age_years: int,
    activity_level: ActivityLevel,
    goal: Goal,
    macro_split: MacroSplit = DEFAULT_MACRO_SPLIT,
) -> DailyGoals:
    """Compose the whole pipeline: body stats in, daily targets out."""
    bmr = calculate_bmr(
        sex=sex, weight_kg=weight_kg, height_cm=height_cm, age_years=age_years
    )
    tdee = calculate_tdee(bmr, activity_level)
    calories = calculate_calorie_goal(tdee, goal)
    return DailyGoals(
        bmr=round(bmr),
        tdee=round(tdee),
        calories=calories,
        macros=calculate_macros(calories, macro_split),
    )


# --------------------------------------------------------------------------
# Logged-food nutrition: scaling a food's per-100 g values by an amount eaten.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Nutrition:
    """Calories and macros for a specific amount of food."""

    calories: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0

    def __add__(self, other: "Nutrition") -> "Nutrition":
        # Defining addition lets a day's entries be combined with the
        # built-in sum(), starting from an empty Nutrition().
        return Nutrition(
            calories=self.calories + other.calories,
            protein_g=self.protein_g + other.protein_g,
            carbs_g=self.carbs_g + other.carbs_g,
            fat_g=self.fat_g + other.fat_g,
        )


def scale_per_100g(
    *,
    calories_per_100g: float,
    protein_per_100g: float,
    carbs_per_100g: float,
    fat_per_100g: float,
    grams: float,
) -> Nutrition:
    """Scale per-100 g nutrition to an arbitrary amount in grams."""
    factor = grams / 100
    return Nutrition(
        calories=calories_per_100g * factor,
        protein_g=protein_per_100g * factor,
        carbs_g=carbs_per_100g * factor,
        fat_g=fat_per_100g * factor,
    )
