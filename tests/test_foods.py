"""Tests for food search."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.seed import seed_foods
from app.models import Food
from app.services import food_service

SIGNUP = {"email": "eater@example.com", "password": "correct-horse-battery"}


def sign_in(client: TestClient) -> None:
    client.post("/api/auth/register", json=SIGNUP)


def make_food(name: str, brand: str | None = None, **overrides: float) -> Food:
    values = {
        "calories_per_100g": 100.0,
        "protein_per_100g": 5.0,
        "carbs_per_100g": 10.0,
        "fat_per_100g": 2.0,
        "serving_size_g": 100.0,
        "serving_label": "100 g",
    }
    values.update(overrides)
    return Food(name=name, brand=brand, **values)


def add(db: Session, *foods: Food) -> None:
    db.add_all(foods)
    db.commit()


# ------------------------------------------------------------ search service
def test_search_matches_name_case_insensitively(db: Session) -> None:
    add(db, make_food("Banana"), make_food("Apple"))

    assert [f.name for f in food_service.search_foods(db, "ban")] == ["Banana"]
    assert food_service.search_foods(db, "BANANA")[0].name == "Banana"


def test_search_matches_brand(db: Session) -> None:
    add(db, make_food("Greek Yogurt", brand="Chobani"), make_food("Banana"))

    results = food_service.search_foods(db, "chobani")

    assert [f.name for f in results] == ["Greek Yogurt"]


def test_search_ranks_prefix_matches_first(db: Session) -> None:
    add(
        db,
        make_food("Ripe Banana"),
        make_food("Banana"),
        make_food("Banana Bread"),
    )

    names = [f.name for f in food_service.search_foods(db, "banana")]

    # "Ripe Banana" only contains the term, so it sorts after the prefixes.
    assert names.index("Banana") < names.index("Ripe Banana")
    assert names.index("Banana Bread") < names.index("Ripe Banana")


def test_search_treats_percent_as_a_literal(db: Session) -> None:
    add(db, make_food("Banana"), make_food("100% Fruit Juice"))

    # If "%" were an unescaped wildcard, this would match everything.
    results = food_service.search_foods(db, "100%")

    assert [f.name for f in results] == ["100% Fruit Juice"]


def test_search_blank_query_returns_nothing(db: Session) -> None:
    add(db, make_food("Banana"))

    assert food_service.search_foods(db, "   ") == []


def test_search_respects_the_limit(db: Session) -> None:
    add(db, *[make_food(f"Bean {i}") for i in range(10)])

    assert len(food_service.search_foods(db, "bean", limit=3)) == 3


# --------------------------------------------------------------- search endpoint
def test_search_endpoint_returns_matches(client: TestClient, db: Session) -> None:
    add(
        db,
        make_food(
            "Banana",
            calories_per_100g=89,
            serving_size_g=118,
            serving_label="1 medium banana",
        ),
    )
    sign_in(client)

    response = client.get("/api/foods/search", params={"q": "banana"})

    assert response.status_code == 200
    food = response.json()[0]
    assert food["name"] == "Banana"
    assert food["calories_per_100g"] == 89
    assert food["serving_label"] == "1 medium banana"


def test_search_endpoint_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/foods/search", params={"q": "banana"})

    assert response.status_code == 401


def test_search_endpoint_requires_a_non_empty_query(client: TestClient) -> None:
    sign_in(client)

    assert client.get("/api/foods/search").status_code == 422
    assert client.get("/api/foods/search", params={"q": ""}).status_code == 422


# ------------------------------------------------------------------ seed script
def test_seed_is_idempotent(db: Session) -> None:
    first = seed_foods(db)
    second = seed_foods(db)

    assert first > 0  # the empty test database gets populated
    assert second == 0  # a second run adds nothing
