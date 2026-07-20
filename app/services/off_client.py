"""Open Food Facts integration: search their catalogue and fetch products.

Open Food Facts (OFF) is a free, open database of millions of food products.
It needs no API key. We use two of their endpoints:

* **full-text search** — the legacy ``/cgi/search.pl``. It is the only public
  free-text search that works reliably enough to build on today (the newer
  dedicated service is frequently down, and the ``/api/v2/search`` endpoint
  ignores free text and only filters by tags). It is **intermittently
  throttled** and answers ``503`` at random even when healthy, so requests
  retry a few times before giving up.
* **fetch one product** — ``/api/v2/product/{barcode}.json`` (solid).

Everything OFF returns is *dirty*: missing fields, energy reported only in
kilojoules, comma decimals ("14,7g"), absent serving sizes, brands as a
comma-joined list. :func:`map_off_product` is the **adapter** that turns one
raw product dict into our clean, validated :class:`OffFood` — or ``None`` when
the product is too incomplete to use. It is a *pure* function (no network),
which is where the tests concentrate.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import httpx

from app.core.config import settings


class OffUnavailableError(Exception):
    """Raised when Open Food Facts cannot be reached or keeps failing.

    Distinct from "no results found": the search endpoint catches this and
    falls back to local results, so a third-party outage *degrades* the
    feature instead of breaking the page.
    """


@dataclass(frozen=True)
class OffFood:
    """One Open Food Facts product mapped into our canonical shape.

    Mirrors the nutrition columns of :class:`~app.models.food.Food` (per
    100 g + serving metadata) plus ``off_id``, the OFF barcode we dedupe and
    re-fetch on. It is deliberately *not* a DB row: search returns these for
    display, and a food is only persisted once it is actually logged.
    """

    off_id: str
    name: str
    brand: str | None
    calories_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fat_per_100g: float
    serving_size_g: float
    serving_label: str


# ---------------------------------------------------------------------------
# Pure mapping (no network) — the adapter.
# ---------------------------------------------------------------------------

# Pure fat is 900 kcal/100 g, the physical ceiling for any real food. A higher
# value is a data-entry error in OFF, so we drop the product rather than log a
# 5000-kcal "banana".
_MAX_KCAL_PER_100G = 900.0

# 1 kcal = 4.184 kJ. Most European products report only kilojoules.
_KJ_PER_KCAL = 4.184

# The exact fields we ask OFF for. Requesting only these keeps responses small
# (a full OFF product has hundreds of fields) and documents precisely what we
# depend on.
OFF_FIELDS = "code,product_name,brands,nutriments,serving_size,serving_quantity"


def _num(value: object) -> float | None:
    """Coerce an OFF value to a finite, non-negative float, or ``None``.

    OFF nutriment values arrive as numbers, numeric strings, ``None``, or the
    occasional empty string — and sometimes with a comma decimal ("14,7").
    Anything that isn't a usable non-negative number is dropped.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num) or num < 0:
        return None
    return num


def _calories_per_100g(nutriments: dict) -> float | None:
    """Kilocalories per 100 g, converting from kJ when kcal is absent.

    Many products (especially European ones) report only kilojoules, so a
    plain ``energy-kcal_100g`` lookup would silently discard them.
    """
    kcal = _num(nutriments.get("energy-kcal_100g"))
    if kcal is not None:
        return kcal
    kj = _num(nutriments.get("energy-kj_100g"))
    if kj is None:
        kj = _num(nutriments.get("energy_100g"))  # defaults to kJ in OFF
    if kj is not None:
        return kj / _KJ_PER_KCAL
    return None


def _serving(raw: dict) -> tuple[float, str]:
    """A serving size in grams and a human label, defaulting to 100 g.

    ``serving_quantity`` is the clean numeric grams when present;
    ``serving_size`` is free text ("15 g", "14,7g", "1 cup"). When neither is
    usable we fall back to 100 g, which the per-100 g math makes a truthful
    default ("100 g" means the per-serving figures equal the per-100 g ones).
    """
    grams = _num(raw.get("serving_quantity"))
    label = (raw.get("serving_size") or "").strip()
    if grams and grams > 0:
        return grams, (label or f"{grams:g} g")
    return 100.0, "100 g"


def _first_brand(brands: object) -> str | None:
    """OFF ``brands`` is a comma-separated list ("Nutella, Ferrero"); take the
    first entry, or ``None`` if empty."""
    if not isinstance(brands, str):
        return None
    first = brands.split(",")[0].strip()
    return first or None


def map_off_product(raw: dict) -> OffFood | None:
    """Map one raw OFF product to an :class:`OffFood`, or ``None`` if unusable.

    A product is unusable without a barcode, a name, or sane calories — the
    three things every downstream feature (dedupe, display, logging) needs.
    Missing individual macros are treated as ``0`` rather than discarding the
    whole product, since a food legitimately can have ~0 g of a macro.
    """
    off_id = str(raw.get("code") or "").strip()
    name = (raw.get("product_name") or "").strip()
    if not off_id or not name:
        return None

    nutriments = raw.get("nutriments") or {}
    calories = _calories_per_100g(nutriments)
    if calories is None or not (0 < calories <= _MAX_KCAL_PER_100G):
        return None

    serving_size_g, serving_label = _serving(raw)
    brand = _first_brand(raw.get("brands"))

    return OffFood(
        off_id=off_id,
        name=name[:200],  # Food.name is String(200)
        brand=brand[:200] if brand else None,
        calories_per_100g=round(calories, 2),
        protein_per_100g=_num(nutriments.get("proteins_100g")) or 0.0,
        carbs_per_100g=_num(nutriments.get("carbohydrates_100g")) or 0.0,
        fat_per_100g=_num(nutriments.get("fat_100g")) or 0.0,
        serving_size_g=serving_size_g,
        serving_label=serving_label[:100],  # Food.serving_label is String(100)
    )


# ---------------------------------------------------------------------------
# HTTP layer.
# ---------------------------------------------------------------------------

_SEARCH_PATH = "/cgi/search.pl"
_PRODUCT_PATH = "/api/v2/product/{barcode}.json"
# 5xx values worth retrying: OFF's throttle (503) plus transient gateway errors.
_RETRYABLE_STATUS = frozenset({502, 503, 504})


def _client(client: httpx.Client | None) -> tuple[httpx.Client, bool]:
    """Return the client to use and whether we own it (and must close it).

    Tests inject their own client backed by a mock transport; production calls
    build a short-lived one configured from ``settings``.
    """
    if client is not None:
        return client, False
    made = httpx.Client(
        base_url=settings.off_base_url,
        timeout=settings.off_timeout_seconds,
        headers={"User-Agent": settings.off_user_agent},
    )
    return made, True


def _get_with_retry(
    client: httpx.Client, url: str, params: dict
) -> httpx.Response:
    """GET ``url``, retrying a few times on OFF's intermittent 5xx throttling.

    ``search.pl`` answers 503 at random even when healthy; a couple of short,
    backing-off retries turn that transient failure into a success instead of
    surfacing it to the user. A network error (timeout, connection refused) is
    retried too, then re-raised as :class:`OffUnavailableError`.
    """
    attempts = settings.off_max_retries + 1
    last_error: str | None = None
    for attempt in range(attempts):
        try:
            resp = client.get(url, params=params)
        except httpx.HTTPError as exc:
            last_error = str(exc) or exc.__class__.__name__
        else:
            if resp.status_code not in _RETRYABLE_STATUS:
                return resp
            last_error = f"HTTP {resp.status_code}"
        if attempt < attempts - 1:
            # Linear backoff: 0.25s, 0.5s, ... — enough to clear a throttle
            # blip without adding noticeable latency to a real search.
            time.sleep(settings.off_retry_backoff_seconds * (attempt + 1))
    raise OffUnavailableError(
        f"Open Food Facts unavailable for {url} ({last_error})"
    )


def search_off(
    term: str, *, client: httpx.Client | None = None, limit: int | None = None
) -> list[OffFood]:
    """Full-text search OFF and return mapped, usable products.

    Returns ``[]`` for a blank term or a genuine no-match. Raises
    :class:`OffUnavailableError` if OFF stays unreachable, so the caller can
    fall back to local results.
    """
    term = term.strip()
    if not term:
        return []

    cli, owns = _client(client)
    try:
        resp = _get_with_retry(
            cli,
            _SEARCH_PATH,
            {
                "search_terms": term,
                "json": 1,
                "page_size": limit or settings.off_search_page_size,
                "fields": OFF_FIELDS,
            },
        )
        if resp.status_code != 200:
            raise OffUnavailableError(f"search.pl status {resp.status_code}")
        try:
            products = resp.json().get("products", [])
        except ValueError as exc:  # e.g. an HTML error page, not JSON
            raise OffUnavailableError("search.pl returned non-JSON") from exc
    finally:
        if owns:
            cli.close()

    mapped = (map_off_product(p) for p in products)
    return [food for food in mapped if food is not None]


def fetch_off_product(
    barcode: str, *, client: httpx.Client | None = None
) -> OffFood | None:
    """Fetch one product by barcode.

    Returns ``None`` if OFF has no such product or it is unusable; raises
    :class:`OffUnavailableError` on a genuine failure. This is what the
    materialise-on-log flow calls so the *server* — never the client — is the
    source of the nutrition we persist.
    """
    barcode = barcode.strip()
    if not barcode:
        return None

    cli, owns = _client(client)
    try:
        resp = _get_with_retry(
            cli, _PRODUCT_PATH.format(barcode=barcode), {"fields": OFF_FIELDS}
        )
        if resp.status_code == 404:
            return None  # v2 returns 404 for an unknown barcode
        if resp.status_code != 200:
            raise OffUnavailableError(f"product status {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise OffUnavailableError("product returned non-JSON") from exc
    finally:
        if owns:
            cli.close()

    # Some deployments answer 200 with ``status: 0`` instead of a 404, and the
    # product may be absent either way.
    product = body.get("product")
    if not product or body.get("status") == 0:
        return None
    return map_off_product(product)
