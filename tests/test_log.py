"""Tests for meal logging."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Food, LogEntry

SIGNUP = {"email": "eater@example.com", "password": "correct-horse-battery"}


def sign_in(client: TestClient) -> None:
    client.post("/api/auth/register", json=SIGNUP)


def add_food(db: Session, name: str = "Chicken Breast", **overrides: float) -> Food:
    values = {
        "brand": None,
        "calories_per_100g": 165.0,
        "protein_per_100g": 31.0,
        "carbs_per_100g": 0.0,
        "fat_per_100g": 3.6,
        "serving_size_g": 100.0,
        "serving_label": "100 g",
    }
    values.update(overrides)
    food = Food(name=name, **values)
    db.add(food)
    db.commit()
    db.refresh(food)
    return food


# ------------------------------------------------------------------- logging
def test_logging_scales_nutrition_by_grams(
    client: TestClient, db: Session
) -> None:
    food = add_food(db)  # 165 kcal, 31 P per 100 g
    sign_in(client)

    response = client.post(
        "/api/log",
        json={"food_id": food.id, "meal_type": "lunch", "quantity_grams": 200},
    )

    assert response.status_code == 201
    body = response.json()
    # 200 g = 2x the per-100 g values.
    assert body["nutrition"]["calories"] == 330
    assert body["nutrition"]["protein_g"] == 62
    assert body["food_name"] == "Chicken Breast"


def test_logging_an_unknown_food_is_404(client: TestClient) -> None:
    sign_in(client)

    response = client.post(
        "/api/log",
        json={"food_id": 999, "meal_type": "lunch", "quantity_grams": 100},
    )

    assert response.status_code == 404


def test_entry_snapshot_survives_a_later_food_change(
    client: TestClient, db: Session
) -> None:
    food = add_food(db, calories_per_100g=165)
    sign_in(client)
    client.post(
        "/api/log",
        json={"food_id": food.id, "meal_type": "lunch", "quantity_grams": 100},
    )

    # The food is corrected long after the entry was logged...
    food.calories_per_100g = 9999
    db.commit()

    # ...but the logged day is unchanged, because it snapshotted the value.
    day = client.get("/api/log").json()
    assert day["entries"][0]["nutrition"]["calories"] == 165


# -------------------------------------------------------------------- the day
def test_day_totals_sum_every_entry(client: TestClient, db: Session) -> None:
    chicken = add_food(db, "Chicken", calories_per_100g=165, protein_per_100g=31)
    rice = add_food(db, "Rice", calories_per_100g=130, protein_per_100g=2.7)
    sign_in(client)
    client.post(
        "/api/log",
        json={"food_id": chicken.id, "meal_type": "lunch", "quantity_grams": 200},
    )
    client.post(
        "/api/log",
        json={"food_id": rice.id, "meal_type": "lunch", "quantity_grams": 100},
    )

    day = client.get("/api/log").json()

    assert len(day["entries"]) == 2
    # 330 (chicken) + 130 (rice) = 460
    assert day["totals"]["calories"] == 460


def test_day_only_returns_the_requested_date(
    client: TestClient, db: Session
) -> None:
    food = add_food(db)
    sign_in(client)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    client.post(
        "/api/log",
        json={
            "food_id": food.id,
            "meal_type": "dinner",
            "quantity_grams": 100,
            "date": yesterday,
        },
    )

    today = client.get("/api/log").json()
    assert today["entries"] == []

    past = client.get("/api/log", params={"date": yesterday}).json()
    assert len(past["entries"]) == 1


# -------------------------------------------------------------------- delete
def test_delete_removes_an_entry(client: TestClient, db: Session) -> None:
    food = add_food(db)
    sign_in(client)
    created = client.post(
        "/api/log",
        json={"food_id": food.id, "meal_type": "snack", "quantity_grams": 50},
    ).json()

    assert client.delete(f"/api/log/{created['id']}").status_code == 204
    assert client.get("/api/log").json()["entries"] == []


def test_cannot_delete_another_users_entry(
    client: TestClient, db: Session
) -> None:
    food = add_food(db)
    sign_in(client)
    created = client.post(
        "/api/log",
        json={"food_id": food.id, "meal_type": "snack", "quantity_grams": 50},
    ).json()
    client.post("/api/auth/logout")

    # A different account must not be able to delete the first user's entry.
    client.post(
        "/api/auth/register",
        json={"email": "someone@example.com", "password": "another-password"},
    )
    response = client.delete(f"/api/log/{created['id']}")

    assert response.status_code == 404


# ---------------------------------------------------------------- validation
def test_logging_rejects_non_positive_quantity(
    client: TestClient, db: Session
) -> None:
    food = add_food(db)
    sign_in(client)

    response = client.post(
        "/api/log",
        json={"food_id": food.id, "meal_type": "lunch", "quantity_grams": 0},
    )

    assert response.status_code == 422


def test_logging_rejects_an_unknown_meal_type(
    client: TestClient, db: Session
) -> None:
    food = add_food(db)
    sign_in(client)

    response = client.post(
        "/api/log",
        json={"food_id": food.id, "meal_type": "brunch", "quantity_grams": 100},
    )

    assert response.status_code == 422


# --------------------------------------------------------------------- auth
def test_log_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/api/log").status_code == 401
    assert (
        client.post(
            "/api/log",
            json={"food_id": 1, "meal_type": "lunch", "quantity_grams": 100},
        ).status_code
        == 401
    )


# ------------------------------------------------- custom (non-catalogue) foods
CUSTOM_URL = "/api/log/custom"
RICE = {
    "name": "Steamed rice",
    "quantity_grams": 180,
    "calories_per_100g": 130,
    "protein_per_100g": 2.7,
    "carbs_per_100g": 28.2,
    "fat_per_100g": 0.3,
}
CHICKEN = {
    "name": "Grilled chicken",
    "quantity_grams": 160,
    "calories_per_100g": 165,
    "protein_per_100g": 31,
    "carbs_per_100g": 0,
    "fat_per_100g": 3.6,
}


def test_custom_items_log_as_ordinary_entries(
    client: TestClient, db: Session
) -> None:
    sign_in(client)

    response = client.post(
        CUSTOM_URL, json={"meal_type": "dinner", "items": [RICE, CHICKEN]}
    )

    assert response.status_code == 201
    created = response.json()
    assert [e["food_name"] for e in created] == ["Steamed rice", "Grilled chicken"]
    assert {e["meal_type"] for e in created} == {"dinner"}
    # 180 g × 130/100 = 234 kcal; 160 g × 165/100 = 264 kcal.
    assert [e["nutrition"]["calories"] for e in created] == [234, 264]
    day = client.get("/api/log").json()
    assert day["totals"]["calories"] == 498
    # Protein: 180 × 2.7/100 = 4.86 plus 160 × 31/100 = 49.6 → 54.46 → 54.
    assert day["totals"]["protein_g"] == 54


def test_custom_entries_never_touch_the_food_catalogue(
    client: TestClient, db: Session
) -> None:
    sign_in(client)

    client.post(CUSTOM_URL, json={"meal_type": "lunch", "items": [RICE]})

    entry = db.scalars(select(LogEntry)).one()
    assert entry.food_id is None  # a snapshot with no food behind it
    assert db.scalar(select(func.count()).select_from(Food)) == 0


def test_custom_entries_can_be_back_dated_and_deleted(
    client: TestClient,
) -> None:
    sign_in(client)
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    (entry,) = client.post(
        CUSTOM_URL,
        json={"meal_type": "snack", "date": yesterday, "items": [RICE]},
    ).json()

    assert entry["date"] == yesterday
    assert client.get("/api/log").json()["entries"] == []  # not today's
    assert client.delete(f"/api/log/{entry['id']}").status_code == 204


@pytest.mark.parametrize(
    "bad_item",
    [
        {**RICE, "calories_per_100g": 950},  # denser than pure fat
        {**RICE, "protein_per_100g": 120},  # more than the food weighs
        {**RICE, "quantity_grams": 0},
        {**RICE, "quantity_grams": 20_000},
        {**RICE, "name": "   "},  # blank once whitespace is stripped
    ],
)
def test_one_bad_item_rejects_the_whole_meal(
    client: TestClient, db: Session, bad_item: dict
) -> None:
    sign_in(client)

    response = client.post(
        CUSTOM_URL, json={"meal_type": "lunch", "items": [CHICKEN, bad_item]}
    )

    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(LogEntry)) == 0


@pytest.mark.parametrize("count", [0, 21])
def test_custom_log_bounds_the_number_of_items(
    client: TestClient, count: int
) -> None:
    sign_in(client)

    response = client.post(
        CUSTOM_URL, json={"meal_type": "lunch", "items": [RICE] * count}
    )

    assert response.status_code == 422


def test_custom_log_requires_authentication(client: TestClient) -> None:
    response = client.post(CUSTOM_URL, json={"meal_type": "lunch", "items": [RICE]})
    assert response.status_code == 401
