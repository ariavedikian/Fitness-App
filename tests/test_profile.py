"""Tests for the profile endpoints and the age helper."""

from datetime import date

from fastapi.testclient import TestClient

from app.services import nutrition, profile_service

SIGNUP = {"email": "lifter@example.com", "password": "correct-horse-battery"}
VALID_PROFILE = {
    "height_cm": 180,
    "weight_kg": 80,
    "birth_date": "1996-01-01",
    "sex": "male",
    "activity_level": "moderate",
    "goal": "maintain",
}


def sign_in(client: TestClient) -> None:
    client.post("/api/auth/register", json=SIGNUP)


# --------------------------------------------------------------- age helper
def test_age_is_full_years_before_this_years_birthday() -> None:
    # Birthday (June 1) has not arrived yet on May 31.
    age = profile_service.age_from_birth_date(
        date(2000, 6, 1), today=date(2026, 5, 31)
    )
    assert age == 25


def test_age_ticks_over_on_the_birthday() -> None:
    age = profile_service.age_from_birth_date(
        date(2000, 6, 1), today=date(2026, 6, 1)
    )
    assert age == 26


# ------------------------------------------------------------------ profile
def test_get_profile_is_404_before_one_exists(client: TestClient) -> None:
    sign_in(client)

    response = client.get("/api/profile")

    assert response.status_code == 404


def test_put_then_get_returns_the_profile(client: TestClient) -> None:
    sign_in(client)

    put = client.put("/api/profile", json=VALID_PROFILE)
    assert put.status_code == 200

    get = client.get("/api/profile")
    assert get.status_code == 200
    body = get.json()
    assert body["height_cm"] == 180
    assert body["sex"] == "male"
    assert body["updated_at"]


def test_put_is_an_upsert_not_a_duplicate(client: TestClient) -> None:
    sign_in(client)
    client.put("/api/profile", json=VALID_PROFILE)

    # Second PUT with new stats should replace, not add a second profile.
    client.put("/api/profile", json={**VALID_PROFILE, "weight_kg": 75})

    body = client.get("/api/profile").json()
    assert body["weight_kg"] == 75


# -------------------------------------------------------------------- goals
def test_goals_run_the_pipeline_over_the_saved_profile(
    client: TestClient,
) -> None:
    sign_in(client)
    client.put("/api/profile", json=VALID_PROFILE)

    body = client.get("/api/profile/goals").json()

    # Recompute independently from the same inputs rather than hard-coding
    # numbers that depend on today's date.
    age = profile_service.age_from_birth_date(date(1996, 1, 1))
    expected = nutrition.calculate_goals(
        sex=nutrition.Sex.MALE,
        weight_kg=80,
        height_cm=180,
        age_years=age,
        activity_level=nutrition.ActivityLevel.MODERATE,
        goal=nutrition.Goal.MAINTAIN,
    )
    assert body["bmr"] == expected.bmr
    assert body["tdee"] == expected.tdee
    assert body["calories"] == expected.calories
    assert body["macros"]["protein_g"] == expected.macros.protein_g


def test_goals_are_404_without_a_profile(client: TestClient) -> None:
    sign_in(client)

    response = client.get("/api/profile/goals")

    assert response.status_code == 404


# --------------------------------------------------------------- validation
def test_put_rejects_a_future_birth_date(client: TestClient) -> None:
    sign_in(client)

    response = client.put(
        "/api/profile", json={**VALID_PROFILE, "birth_date": "2999-01-01"}
    )

    assert response.status_code == 422


def test_put_rejects_an_under_age_user(client: TestClient) -> None:
    sign_in(client)
    recent = date.today().replace(year=date.today().year - 10).isoformat()

    response = client.put(
        "/api/profile", json={**VALID_PROFILE, "birth_date": recent}
    )

    assert response.status_code == 422


def test_put_rejects_a_nonsense_height(client: TestClient) -> None:
    sign_in(client)

    response = client.put(
        "/api/profile", json={**VALID_PROFILE, "height_cm": 0}
    )

    assert response.status_code == 422


def test_put_rejects_an_unknown_activity_level(client: TestClient) -> None:
    sign_in(client)

    response = client.put(
        "/api/profile", json={**VALID_PROFILE, "activity_level": "olympian"}
    )

    assert response.status_code == 422


# --------------------------------------------------------------------- auth
def test_profile_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/api/profile").status_code == 401
    assert client.put("/api/profile", json=VALID_PROFILE).status_code == 401
    assert client.get("/api/profile/goals").status_code == 401
