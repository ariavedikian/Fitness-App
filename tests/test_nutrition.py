"""Tests for the pure nutrition calculations.

Expected values are worked out by hand in the comments so a failure points
at the arithmetic, not at a mystery constant.
"""

import pytest

from app.services.nutrition import (
    ActivityLevel,
    DailyGoals,
    Goal,
    MacroSplit,
    Nutrition,
    Sex,
    calculate_bmr,
    calculate_calorie_goal,
    calculate_goals,
    calculate_macros,
    calculate_tdee,
    scale_per_100g,
)


def test_bmr_for_a_male() -> None:
    # 10*80 + 6.25*180 - 5*30 + 5 = 800 + 1125 - 150 + 5 = 1780
    bmr = calculate_bmr(sex=Sex.MALE, weight_kg=80, height_cm=180, age_years=30)
    assert bmr == pytest.approx(1780)


def test_bmr_for_a_female() -> None:
    # 10*65 + 6.25*165 - 5*30 - 161 = 650 + 1031.25 - 150 - 161 = 1370.25
    bmr = calculate_bmr(sex=Sex.FEMALE, weight_kg=65, height_cm=165, age_years=30)
    assert bmr == pytest.approx(1370.25)


def test_only_the_sex_constant_differs_between_sexes() -> None:
    # The two Mifflin-St Jeor constants are +5 and -161, a gap of 166.
    same = {"weight_kg": 70, "height_cm": 175, "age_years": 40}
    male = calculate_bmr(sex=Sex.MALE, **same)
    female = calculate_bmr(sex=Sex.FEMALE, **same)
    assert male - female == pytest.approx(166)


def test_tdee_scales_bmr_by_activity() -> None:
    # 1780 * 1.55 (moderate) = 2759
    assert calculate_tdee(1780, ActivityLevel.MODERATE) == pytest.approx(2759)


def test_more_activity_always_means_more_energy() -> None:
    levels = [
        ActivityLevel.SEDENTARY,
        ActivityLevel.LIGHT,
        ActivityLevel.MODERATE,
        ActivityLevel.ACTIVE,
        ActivityLevel.VERY_ACTIVE,
    ]
    tdees = [calculate_tdee(1780, level) for level in levels]
    assert tdees == sorted(tdees)
    assert len(set(tdees)) == len(tdees)  # strictly increasing, no ties


@pytest.mark.parametrize(
    ("goal", "expected"),
    [(Goal.LOSE, 2259), (Goal.MAINTAIN, 2759), (Goal.GAIN, 3259)],
)
def test_calorie_goal_adjusts_maintenance_by_500(
    goal: Goal, expected: int
) -> None:
    assert calculate_calorie_goal(2759, goal) == expected


def test_macros_split_calories_correctly() -> None:
    # 2000 kcal at 30/40/30:
    #   protein 2000*0.30/4 = 150 g
    #   carbs   2000*0.40/4 = 200 g
    #   fat     2000*0.30/9 = 66.7 -> 67 g
    macros = calculate_macros(2000)
    assert (macros.protein_g, macros.carbs_g, macros.fat_g) == (150, 200, 67)


def test_macro_grams_reconstruct_the_calorie_total() -> None:
    # Grams converted back to calories should land within rounding of the
    # original target.
    calories = 2200
    m = calculate_macros(calories)
    reconstructed = m.protein_g * 4 + m.carbs_g * 4 + m.fat_g * 9
    assert reconstructed == pytest.approx(calories, abs=10)


def test_macro_split_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        MacroSplit(protein=0.5, carbs=0.5, fat=0.5)


def test_calculate_goals_composes_the_whole_pipeline() -> None:
    goals = calculate_goals(
        sex=Sex.MALE,
        weight_kg=80,
        height_cm=180,
        age_years=30,
        activity_level=ActivityLevel.MODERATE,
        goal=Goal.MAINTAIN,
    )
    assert isinstance(goals, DailyGoals)
    assert goals.bmr == 1780
    assert goals.tdee == 2759
    assert goals.calories == 2759
    # Macros derived from the 2759 target, not a fixed number.
    assert goals.macros.protein_g == round(2759 * 0.30 / 4)


def test_scale_per_100g_multiplies_by_the_amount() -> None:
    # 200 g of a 165 kcal / 31 g-protein per-100 g food = 2x.
    n = scale_per_100g(
        calories_per_100g=165,
        protein_per_100g=31,
        carbs_per_100g=0,
        fat_per_100g=3.6,
        grams=200,
    )
    assert n.calories == pytest.approx(330)
    assert n.protein_g == pytest.approx(62)
    assert n.fat_g == pytest.approx(7.2)


def test_nutrition_adds_componentwise() -> None:
    total = Nutrition(100, 10, 20, 5) + Nutrition(50, 4, 8, 1)
    assert (total.calories, total.protein_g, total.carbs_g, total.fat_g) == (
        150,
        14,
        28,
        6,
    )


def test_nutrition_sums_from_empty() -> None:
    # The empty Nutrition() is the identity that makes sum() work.
    parts = [Nutrition(100, 10, 20, 5), Nutrition(200, 20, 40, 10)]
    assert sum(parts, Nutrition()).calories == 300
