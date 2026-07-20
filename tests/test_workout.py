"""Tests for the pure workout calculations.

Expected values are worked out by hand in the comments so a failure points at
the arithmetic, not at a mystery constant.
"""

import pytest

from app.services.workout import ExerciseType, estimate_calories_burned


def test_met_formula_for_a_run() -> None:
    # 30 min running (MET 8) at 70 kg → 8 * 70 * (30/60) = 280 kcal.
    burned = estimate_calories_burned(met=8, weight_kg=70, minutes=30)
    assert burned == pytest.approx(280)


def test_one_met_for_one_hour_is_one_kcal_per_kg() -> None:
    # The MET definition: 1 MET for 1 hour ≈ 1 kcal per kg of body weight.
    assert estimate_calories_burned(met=1, weight_kg=70, minutes=60) == pytest.approx(70)


def test_calories_scale_linearly_with_duration() -> None:
    base = estimate_calories_burned(met=6, weight_kg=80, minutes=30)
    twice = estimate_calories_burned(met=6, weight_kg=80, minutes=60)
    assert twice == pytest.approx(2 * base)


def test_calories_scale_linearly_with_body_weight() -> None:
    light = estimate_calories_burned(met=5, weight_kg=50, minutes=60)
    heavy = estimate_calories_burned(met=5, weight_kg=100, minutes=60)
    assert heavy == pytest.approx(2 * light)


def test_zero_duration_burns_nothing() -> None:
    assert estimate_calories_burned(met=8, weight_kg=70, minutes=0) == 0


def test_result_is_left_unrounded() -> None:
    # 20 min cycling (MET 7.5) at 73 kg → 7.5 * 73 * (20/60) = 182.5 exactly.
    assert estimate_calories_burned(met=7.5, weight_kg=73, minutes=20) == pytest.approx(
        182.5
    )


def test_exercise_type_stored_by_value() -> None:
    assert ExerciseType.CARDIO.value == "cardio"
    assert ExerciseType.STRENGTH.value == "strength"
