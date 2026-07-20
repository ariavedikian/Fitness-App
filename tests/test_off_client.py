"""Tests for the Open Food Facts integration.

Two halves:

* the **adapter** (:func:`map_off_product`) is pure, so it is tested directly
  against hand-built raw product dicts that reproduce OFF's real messiness;
* the **HTTP layer** is tested with an ``httpx.MockTransport`` so no test ever
  touches the network — we drive exact status codes and payloads, including
  the intermittent 503s that motivated the retry logic.
"""

import httpx
import pytest

from app.services import off_client
from app.services.off_client import (
    OFF_FIELDS,
    OffFood,
    OffUnavailableError,
    fetch_off_product,
    map_off_product,
    search_off,
)


def _raw(**overrides: object) -> dict:
    """A complete, valid raw OFF product; override individual fields per test."""
    base = {
        "code": "3017620422003",
        "product_name": "Nutella",
        "brands": "Nutella, Ferrero",
        "nutriments": {
            "energy-kcal_100g": 539,
            "proteins_100g": 6.3,
            "carbohydrates_100g": 57.5,
            "fat_100g": 30.9,
        },
        "serving_size": "15 g",
        "serving_quantity": 15,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# The adapter: map_off_product.
# ---------------------------------------------------------------------------


def test_maps_a_complete_product() -> None:
    food = map_off_product(_raw())
    assert food == OffFood(
        off_id="3017620422003",
        name="Nutella",
        brand="Nutella",  # first of the comma-separated brands
        calories_per_100g=539.0,
        protein_per_100g=6.3,
        carbs_per_100g=57.5,
        fat_per_100g=30.9,
        serving_size_g=15.0,
        serving_label="15 g",
    )


def test_takes_only_the_first_brand() -> None:
    # OFF stores brands as a comma-separated list; we keep the first.
    assert map_off_product(_raw(brands="Nutella, Ferrero")).brand == "Nutella"
    assert map_off_product(_raw(brands="  Ferrero  ")).brand == "Ferrero"
    assert map_off_product(_raw(brands="")).brand is None
    assert map_off_product(_raw(brands=None)).brand is None


def test_missing_name_is_unusable() -> None:
    assert map_off_product(_raw(product_name="")) is None
    assert map_off_product(_raw(product_name="   ")) is None
    raw = _raw()
    del raw["product_name"]
    assert map_off_product(raw) is None


def test_missing_barcode_is_unusable() -> None:
    assert map_off_product(_raw(code="")) is None
    raw = _raw()
    del raw["code"]
    assert map_off_product(raw) is None


def test_missing_calories_is_unusable() -> None:
    # Calories are the headline number; without them the food is useless.
    assert map_off_product(_raw(nutriments={"proteins_100g": 6})) is None


def test_derives_kcal_from_kilojoules() -> None:
    # Many European products report only kJ. 1000 kJ / 4.184 = 239.0 kcal.
    food = map_off_product(
        _raw(nutriments={"energy-kj_100g": 1000, "proteins_100g": 5})
    )
    assert food.calories_per_100g == pytest.approx(239.0, abs=0.1)


def test_prefers_kcal_over_kilojoules() -> None:
    # When both are present, the explicit kcal figure wins (no conversion).
    food = map_off_product(
        _raw(nutriments={"energy-kcal_100g": 200, "energy-kj_100g": 9999})
    )
    assert food.calories_per_100g == 200.0


def test_missing_macros_default_to_zero() -> None:
    # A missing macro shouldn't discard the product — treat it as 0 g.
    food = map_off_product(_raw(nutriments={"energy-kcal_100g": 100}))
    assert (food.protein_per_100g, food.carbs_per_100g, food.fat_per_100g) == (
        0.0,
        0.0,
        0.0,
    )


def test_rejects_physically_impossible_calories() -> None:
    # Nothing real exceeds 900 kcal/100 g (pure fat); a 5000 is a data error.
    assert map_off_product(_raw(nutriments={"energy-kcal_100g": 5000})) is None
    assert map_off_product(_raw(nutriments={"energy-kcal_100g": 0})) is None
    assert map_off_product(_raw(nutriments={"energy-kcal_100g": -10})) is None


def test_coerces_dirty_numeric_values() -> None:
    # OFF numbers can be strings, comma decimals, or junk.
    food = map_off_product(
        _raw(
            nutriments={
                "energy-kcal_100g": "150",
                "proteins_100g": "3,5",  # European comma decimal
                "carbohydrates_100g": "not a number",
                "fat_100g": None,
            }
        )
    )
    assert food.calories_per_100g == 150.0
    assert food.protein_per_100g == 3.5
    assert food.carbs_per_100g == 0.0  # junk -> 0
    assert food.fat_per_100g == 0.0  # None -> 0


def test_serving_prefers_numeric_quantity() -> None:
    food = map_off_product(_raw(serving_quantity=30, serving_size="30 g"))
    assert food.serving_size_g == 30.0
    assert food.serving_label == "30 g"


def test_serving_defaults_to_100g_when_absent() -> None:
    # No serving info at all -> an honest per-100 g default.
    food = map_off_product(_raw(serving_quantity=None, serving_size=None))
    assert food.serving_size_g == 100.0
    assert food.serving_label == "100 g"


def test_serving_labels_from_quantity_when_only_number_present() -> None:
    food = map_off_product(_raw(serving_quantity=14.7, serving_size=None))
    assert food.serving_size_g == 14.7
    assert food.serving_label == "14.7 g"


def test_truncates_overlong_text_to_column_limits() -> None:
    food = map_off_product(_raw(product_name="x" * 300, brands="y" * 300))
    assert len(food.name) == 200  # Food.name is String(200)
    assert len(food.brand) == 200


# ---------------------------------------------------------------------------
# The HTTP layer: search_off and fetch_off_product.
# ---------------------------------------------------------------------------


def _client(handler) -> httpx.Client:
    """A client whose requests are answered by ``handler`` instead of the
    network. ``base_url`` is a dummy — the mock transport ignores the host."""
    return httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://off.test"
    )


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep retry tests fast: the backoff sleep does nothing in tests."""
    monkeypatch.setattr(off_client.time, "sleep", lambda _seconds: None)


def test_search_maps_and_drops_unusable_results() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "products": [
                    _raw(code="1", product_name="Good"),
                    _raw(code="2", product_name=""),  # unusable -> dropped
                ]
            },
        )

    with _client(handler) as cli:
        results = search_off("banana", client=cli)

    assert [f.name for f in results] == ["Good"]


def test_search_requests_only_the_fields_we_need() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"products": []})

    with _client(handler) as cli:
        search_off("banana", client=cli, limit=7)

    assert seen["params"]["search_terms"] == "banana"
    assert seen["params"]["fields"] == OFF_FIELDS
    assert seen["params"]["page_size"] == "7"
    assert seen["params"]["json"] == "1"


def test_search_retries_past_intermittent_503() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="temporarily unavailable")
        return httpx.Response(200, json={"products": [_raw(product_name="Ok")]})

    with _client(handler) as cli:
        results = search_off("banana", client=cli)

    assert calls["n"] == 3  # two 503s, then success
    assert [f.name for f in results] == ["Ok"]


def test_search_gives_up_after_persistent_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(off_client.settings, "off_max_retries", 2)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="temporarily unavailable")

    with _client(handler) as cli:
        with pytest.raises(OffUnavailableError):
            search_off("banana", client=cli)


def test_search_raises_on_non_json_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with _client(handler) as cli:
        with pytest.raises(OffUnavailableError):
            search_off("banana", client=cli)


def test_search_blank_term_makes_no_request() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not be called for a blank term")

    with _client(handler) as cli:
        assert search_off("   ", client=cli) == []


def test_fetch_product_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/3017620422003.json")
        return httpx.Response(200, json={"status": 1, "product": _raw()})

    with _client(handler) as cli:
        food = fetch_off_product("3017620422003", client=cli)

    assert food is not None and food.name == "Nutella"


def test_fetch_product_404_returns_none() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"status": 0})

    with _client(handler) as cli:
        assert fetch_off_product("0000", client=cli) is None


def test_fetch_product_status_zero_returns_none() -> None:
    # Some OFF responses use 200 + status:0 instead of a 404.
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": 0, "product": None})

    with _client(handler) as cli:
        assert fetch_off_product("0000", client=cli) is None


def test_fetch_product_raises_on_server_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with _client(handler) as cli:
        with pytest.raises(OffUnavailableError):
            fetch_off_product("3017620422003", client=cli)
