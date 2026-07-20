"""Seed the reference catalogues (foods and exercises).

Run after migrating:

    python -m app.db.seed

Idempotent: an entry already present (foods matched on name + brand, exercises
on name) is skipped, so re-running after adding new rows only inserts the new
ones. Reference data lives in a seed script rather than a migration because it
is content, not schema — you may want to reshape or reload it without touching
table history.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Exercise, Food
from app.services.workout import ExerciseType

# name, brand, kcal, protein, carbs, fat, serving_g, serving_label
#   — nutrition values are per 100 g.
_FOODS: list[tuple[str, str | None, float, float, float, float, float, str]] = [
    ("Banana", None, 89, 1.1, 22.8, 0.3, 118, "1 medium banana"),
    ("Apple", None, 52, 0.3, 13.8, 0.2, 182, "1 medium apple"),
    ("Orange", None, 47, 0.9, 11.8, 0.1, 131, "1 medium orange"),
    ("Strawberries", None, 32, 0.7, 7.7, 0.3, 152, "1 cup, halves"),
    ("Blueberries", None, 57, 0.7, 14.5, 0.3, 148, "1 cup"),
    ("Avocado", None, 160, 2.0, 8.5, 14.7, 150, "1 medium avocado"),
    ("Chicken Breast, cooked", None, 165, 31.0, 0.0, 3.6, 100, "100 g"),
    ("Ground Beef, 85% lean, cooked", None, 250, 26.0, 0.0, 15.0, 100, "100 g"),
    ("Salmon, cooked", None, 208, 20.0, 0.0, 13.0, 100, "100 g"),
    ("Tuna, canned in water", None, 116, 26.0, 0.0, 0.8, 142, "1 can, drained"),
    ("Large Egg", None, 155, 13.0, 1.1, 11.0, 50, "1 large egg"),
    ("Whole Milk", None, 61, 3.2, 4.8, 3.3, 244, "1 cup"),
    ("Greek Yogurt, plain nonfat", "Chobani", 59, 10.0, 3.6, 0.4, 170, "1 container"),
    ("Cheddar Cheese", None, 403, 25.0, 1.3, 33.0, 28, "1 oz"),
    ("Cottage Cheese, low-fat", None, 98, 11.0, 3.4, 4.3, 226, "1 cup"),
    ("White Rice, cooked", None, 130, 2.7, 28.0, 0.3, 158, "1 cup, cooked"),
    ("Brown Rice, cooked", None, 123, 2.7, 25.6, 1.0, 195, "1 cup, cooked"),
    ("Quinoa, cooked", None, 120, 4.4, 21.3, 1.9, 185, "1 cup, cooked"),
    ("Pasta, cooked", None, 131, 5.0, 25.0, 1.1, 140, "1 cup, cooked"),
    ("Oats, rolled dry", "Quaker", 389, 16.9, 66.3, 6.9, 40, "1/2 cup dry"),
    ("White Bread", None, 265, 9.0, 49.0, 3.2, 28, "1 slice"),
    ("Whole Wheat Bread", None, 247, 13.0, 41.0, 3.4, 28, "1 slice"),
    ("Baked Potato", None, 93, 2.5, 21.0, 0.1, 173, "1 medium"),
    ("Sweet Potato, baked", None, 90, 2.0, 20.7, 0.1, 151, "1 medium"),
    ("Broccoli", None, 34, 2.8, 6.6, 0.4, 91, "1 cup, chopped"),
    ("Spinach, raw", None, 23, 2.9, 3.6, 0.4, 30, "1 cup"),
    ("Black Beans, cooked", None, 132, 8.9, 23.7, 0.5, 172, "1 cup"),
    ("Almonds", None, 579, 21.2, 21.6, 49.9, 28, "1 oz (23 almonds)"),
    ("Peanut Butter", None, 588, 25.0, 20.0, 50.0, 32, "2 tbsp"),
    ("Olive Oil", None, 884, 0.0, 0.0, 100.0, 14, "1 tbsp"),
]


def _food_exists(db: Session, name: str, brand: str | None) -> bool:
    stmt = select(Food.id).where(Food.name == name)
    stmt = (
        stmt.where(Food.brand.is_(None))
        if brand is None
        else stmt.where(Food.brand == brand)
    )
    return db.scalar(stmt) is not None


def seed_foods(db: Session) -> int:
    """Insert any reference foods not already present. Returns how many added."""
    added = 0
    for name, brand, kcal, protein, carbs, fat, serving_g, label in _FOODS:
        if _food_exists(db, name, brand):
            continue
        db.add(
            Food(
                name=name,
                brand=brand,
                calories_per_100g=kcal,
                protein_per_100g=protein,
                carbs_per_100g=carbs,
                fat_per_100g=fat,
                serving_size_g=serving_g,
                serving_label=label,
            )
        )
        added += 1

    db.commit()
    return added


# name, type, MET, muscle_group.
#   - Cardio rows carry a MET (kcal per kg per hour) for calorie estimation and
#     no muscle group; strength rows carry a muscle group and no MET (we don't
#     estimate strength calories — there's no duration to base them on).
#   - MET values follow the Compendium of Physical Activities (rounded).
_C = ExerciseType.CARDIO
_S = ExerciseType.STRENGTH
_EXERCISES: list[tuple[str, ExerciseType, float | None, str | None]] = [
    # Cardio
    ("Running", _C, 9.8, None),
    ("Walking", _C, 3.5, None),
    ("Cycling", _C, 7.5, None),
    ("Swimming", _C, 7.0, None),
    ("Rowing Machine", _C, 7.0, None),
    ("Elliptical Trainer", _C, 5.0, None),
    ("Stair Climbing", _C, 8.0, None),
    ("Jump Rope", _C, 12.3, None),
    ("Hiking", _C, 6.0, None),
    ("HIIT", _C, 8.0, None),
    ("Boxing", _C, 7.8, None),
    ("Dancing", _C, 5.0, None),
    ("Yoga", _C, 2.5, None),
    ("Elliptical Intervals", _C, 6.8, None),
    # Strength
    ("Bench Press", _S, None, "Chest"),
    ("Push-up", _S, None, "Chest"),
    ("Dumbbell Fly", _S, None, "Chest"),
    ("Squat", _S, None, "Legs"),
    ("Lunge", _S, None, "Legs"),
    ("Leg Press", _S, None, "Legs"),
    ("Leg Curl", _S, None, "Legs"),
    ("Deadlift", _S, None, "Back"),
    ("Bent-over Row", _S, None, "Back"),
    ("Pull-up", _S, None, "Back"),
    ("Lat Pulldown", _S, None, "Back"),
    ("Overhead Press", _S, None, "Shoulders"),
    ("Bicep Curl", _S, None, "Arms"),
    ("Tricep Extension", _S, None, "Arms"),
    ("Plank", _S, None, "Core"),
    ("Crunch", _S, None, "Core"),
]


def _exercise_exists(db: Session, name: str) -> bool:
    return db.scalar(select(Exercise.id).where(Exercise.name == name)) is not None


def seed_exercises(db: Session) -> int:
    """Insert any reference exercises not already present. Returns how many added."""
    added = 0
    for name, type_, met, muscle_group in _EXERCISES:
        if _exercise_exists(db, name):
            continue
        db.add(Exercise(name=name, type=type_, met=met, muscle_group=muscle_group))
        added += 1

    db.commit()
    return added


def main() -> None:
    db = SessionLocal()
    try:
        foods_added = seed_foods(db)
        foods_total = db.scalar(select(func.count()).select_from(Food))
        exercises_added = seed_exercises(db)
        exercises_total = db.scalar(select(func.count()).select_from(Exercise))
        print(
            f"Seeded {foods_added} new food(s); {foods_total} total.\n"
            f"Seeded {exercises_added} new exercise(s); {exercises_total} total."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
