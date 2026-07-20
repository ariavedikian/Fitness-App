"""Pydantic schemas for foods."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FoodImportRequest(BaseModel):
    """Request to import an Open Food Facts product into our database.

    Only the barcode is sent: the server re-fetches the product's nutrition
    from OFF itself rather than trusting numbers from the client, so the data
    we persist has a single, authoritative source.
    """

    off_id: str = Field(min_length=1, max_length=50)


class FoodRead(BaseModel):
    """A single, concrete local food (has a real ``id``).

    Exposes the canonical per-100 g nutrition plus the serving metadata; the
    client derives per-serving figures for display, keeping one source of
    truth on the wire. Returned by the import endpoint once an Open Food Facts
    result has been materialised into our database.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str | None
    calories_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fat_per_100g: float
    serving_size_g: float
    serving_label: str


class FoodSearchResult(BaseModel):
    """One food-search hit — from our local database or from Open Food Facts.

    Search returns a single flat list of these; ``source`` tells the client how
    to log each one:

    * ``"local"`` — a food already in our database. It has a real ``id`` and is
      logged directly (``POST /api/log`` with that ``food_id``).
    * ``"off"`` — an Open Food Facts result. It has an ``off_id`` (barcode) but
      no local ``id`` yet, so it must be imported first; the log dialog does
      that on the user's behalf, turning it into a local food before logging.

    The nutrition fields are identical for both sources, so the client renders
    every hit the same way and only branches on ``source`` at log time.
    """

    # A discriminator beats "guess from whichever id is null": it is explicit,
    # self-documenting, and leaves room for more sources later (e.g. USDA).
    source: Literal["local", "off"]
    id: int | None = None  # set iff source == "local"
    off_id: str | None = None  # set iff source == "off"

    name: str
    brand: str | None
    calories_per_100g: float
    protein_per_100g: float
    carbs_per_100g: float
    fat_per_100g: float
    serving_size_g: float
    serving_label: str


# Whether the external source (Open Food Facts) contributed to this search:
#   "ok"          — OFF answered; its results are included.
#   "unavailable" — OFF was enabled but down/timed out; local results only.
#   "disabled"    — OFF is switched off in config; local results only.
ExternalStatus = Literal["ok", "unavailable", "disabled"]


class FoodSearchResponse(BaseModel):
    """The search endpoint's reply: the hits plus how the external source fared.

    Wrapping the list (rather than returning a bare array) lets the UI tell
    "no external matches" apart from "external search is down" and show an
    honest notice instead of silently pretending OFF's catalogue is empty.
    """

    results: list[FoodSearchResult]
    external: ExternalStatus
