"""Tests for food search."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.seed import seed_foods
from app.models import Food
from app.services import food_service, off_client
from app.services.off_client import OffFood, OffUnavailableError

SIGNUP = {"email": "eater@example.com", "password": "correct-horse-battery"}


def sign_in(client: TestClient) -> None:
    client.post("/api/auth/register", json=SIGNUP)


def make_food(
    name: str,
    brand: str | None = None,
    off_id: str | None = None,
    **overrides: float,
) -> Food:
    values = {
        "calories_per_100g": 100.0,
        "protein_per_100g": 5.0,
        "carbs_per_100g": 10.0,
        "fat_per_100g": 2.0,
        "serving_size_g": 100.0,
        "serving_label": "100 g",
    }
    values.update(overrides)
    return Food(name=name, brand=brand, off_id=off_id, **values)


def add(db: Session, *foods: Food) -> None:
    db.add_all(foods)
    db.commit()


def make_off_food(name: str, off_id: str, brand: str | None = None) -> OffFood:
    """An Open Food Facts result, as off_client.search_off would return it."""
    return OffFood(
        off_id=off_id,
        name=name,
        brand=brand,
        calories_per_100g=100.0,
        protein_per_100g=5.0,
        carbs_per_100g=10.0,
        fat_per_100g=2.0,
        serving_size_g=100.0,
        serving_label="100 g",
    )


def use_off(monkeypatch: pytest.MonkeyPatch, results=None, *, raises=None) -> None:
    """Enable the OFF path and stub what search_off returns (or raises).

    The autouse ``_offline`` fixture disables OFF; a test opts back in here and
    supplies a fake so it still never touches the network.
    """
    monkeypatch.setattr(settings, "off_enabled", True)

    def fake_search_off(query: str, **kwargs) -> list[OffFood]:
        if raises is not None:
            raise raises
        return results or []

    monkeypatch.setattr(off_client, "search_off", fake_search_off)


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
def test_search_endpoint_returns_local_matches(
    client: TestClient, db: Session
) -> None:
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
    body = response.json()
    assert body["external"] == "disabled"  # OFF off by default in tests
    food = body["results"][0]
    assert food["source"] == "local"
    assert food["id"] is not None
    assert food["off_id"] is None
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


# ------------------------------------------------------- hybrid search (local + OFF)
def test_search_merges_local_then_off(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    add(db, make_food("Banana"))
    use_off(monkeypatch, [make_off_food("Banana Bread", off_id="111")])
    sign_in(client)

    body = client.get("/api/foods/search", params={"q": "banana"}).json()

    assert body["external"] == "ok"
    # Local first, then OFF.
    assert [(r["source"], r["name"]) for r in body["results"]] == [
        ("local", "Banana"),
        ("off", "Banana Bread"),
    ]
    off_hit = body["results"][1]
    assert off_hit["id"] is None
    assert off_hit["off_id"] == "111"


def test_search_dedupes_off_against_already_imported_food(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # We already imported the OFF product with barcode 222 as a local food.
    add(db, make_food("Nutella", off_id="222"))
    use_off(
        monkeypatch,
        [
            make_off_food("Nutella", off_id="222"),  # same product -> dropped
            make_off_food("Nutella Biscuits", off_id="333"),  # new -> kept
        ],
    )
    sign_in(client)

    body = client.get("/api/foods/search", params={"q": "nutella"}).json()

    # The imported product appears once (as the local copy), not twice.
    assert [(r["source"], r["off_id"]) for r in body["results"]] == [
        ("local", None),
        ("off", "333"),
    ]


def test_search_degrades_to_local_when_off_unavailable(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    add(db, make_food("Banana"))
    use_off(monkeypatch, raises=OffUnavailableError("down"))
    sign_in(client)

    body = client.get("/api/foods/search", params={"q": "banana"}).json()

    assert body["external"] == "unavailable"
    assert [r["name"] for r in body["results"]] == ["Banana"]  # local survives


def test_search_reports_external_disabled(
    client: TestClient, db: Session
) -> None:
    add(db, make_food("Banana"))
    sign_in(client)

    body = client.get("/api/foods/search", params={"q": "banana"}).json()

    assert body["external"] == "disabled"


# ------------------------------------------------- import (materialise on Add)
def test_import_creates_a_local_food(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        off_client,
        "fetch_off_product",
        lambda off_id, **kw: make_off_food("Nutella", off_id="222", brand="Ferrero"),
    )
    sign_in(client)

    response = client.post("/api/foods/import", json={"off_id": "222"})

    assert response.status_code == 200
    food = response.json()
    assert food["id"] is not None
    assert food["name"] == "Nutella"
    # It is now a real local row, loggable by that id.
    row = db.scalar(select(Food).where(Food.off_id == "222"))
    assert row is not None and row.id == food["id"]


def test_import_is_idempotent_and_skips_off_when_already_local(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    add(db, make_food("Nutella", off_id="222"))

    def fail(*args, **kwargs):  # must not be called — we already have it
        raise AssertionError("OFF should not be hit for an imported barcode")

    monkeypatch.setattr(off_client, "fetch_off_product", fail)
    sign_in(client)

    response = client.post("/api/foods/import", json={"off_id": "222"})

    assert response.status_code == 200
    # Still exactly one row for that barcode.
    assert len(db.scalars(select(Food).where(Food.off_id == "222")).all()) == 1


def test_import_404_when_product_not_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(off_client, "fetch_off_product", lambda off_id, **kw: None)
    sign_in(client)

    response = client.post("/api/foods/import", json={"off_id": "000"})

    assert response.status_code == 404


def test_import_503_when_off_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(*args, **kwargs):
        raise OffUnavailableError("down")

    monkeypatch.setattr(off_client, "fetch_off_product", down)
    sign_in(client)

    response = client.post("/api/foods/import", json={"off_id": "222"})

    assert response.status_code == 503


def test_import_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/foods/import", json={"off_id": "222"})

    assert response.status_code == 401


# ------------------------------------------------------------------ seed script
def test_seed_is_idempotent(db: Session) -> None:
    first = seed_foods(db)
    second = seed_foods(db)

    assert first > 0  # the empty test database gets populated
    assert second == 0  # a second run adds nothing
