"""Claude integration: meal suggestions and photo calorie estimates.

This module is the **adapter** that quarantines the Anthropic SDK, the way
``off_client`` quarantines Open Food Facts: nothing else in the app imports
``anthropic``. Two features use it:

* :func:`recommend_meals` — a :class:`MealRequest` (plain numbers the server
  computed) in, validated :class:`MealSuggestion` objects out;
* :func:`estimate_photo` — a validated image in, a :class:`PhotoEstimate`
  (items with grams and per-100 g nutrition) out.

Each feature has a **pure** half (prompts, prompt builders, Pydantic result
schemas — no network, tested directly) and goes through one shared SDK call,
:func:`_call`, which uses ``client.messages.parse()`` with the schema: the
reply is constrained to matching JSON and validated into Pydantic objects, so
there is no hand-parsing.

Every failure — feature off, no key, API error, refusal, a reply that fails
validation — becomes :class:`AiUnavailableError`, so the caller can *degrade*
("unavailable") instead of breaking the page.

Meal prompts carry only server-computed numbers and an enum — never text the
user typed. A photo *can* contain text (a sign, a label), but the output
schema bounds what it could do: at worst odd items, which the user reviews
before anything is logged.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Literal

import anthropic
import pydantic
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.log_entry import MealType
from app.services.nutrition import Nutrition

logger = logging.getLogger(__name__)


class AiUnavailableError(Exception):
    """Raised when meal suggestions can't be produced right now.

    Covers the feature being switched off or unconfigured as well as genuine
    failures (network, API errors, refusals, unusable replies). Like
    :class:`~app.services.off_client.OffUnavailableError`, it lets the caller
    degrade the feature instead of erroring the page.
    """


# ---------------------------------------------------------------------------
# Request and result shapes.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MealRequest:
    """What we ask for: ideas that fit what's left of today's budget.

    ``remaining`` is computed by the server (goals minus what's been eaten,
    calories net of exercise); this module only formats it. ``meal_type``
    lets Claude size a snack differently from a dinner; ``None`` means any.
    """

    remaining: Nutrition
    meal_type: MealType | None = None
    count: int = 3


class MealSuggestion(BaseModel):
    """One meal idea with Claude's estimate of its nutrition.

    Field descriptions are sent to Claude inside the JSON schema, so they
    double as instructions. Numbers are whole: they estimate a described
    portion, and decimals would claim precision they don't have. ``ge=0``
    is beyond what the API's schema grammar enforces, so the SDK appends it
    to the description as a hint and then enforces it when validating.
    """

    name: str = Field(description="Short meal name, e.g. 'Chicken rice bowl'.")
    description: str = Field(
        description="One or two sentences: the main ingredients and the "
        "portion size the nutrition estimate assumes."
    )
    calories: int = Field(ge=0, description="Estimated kcal for that portion.")
    protein_g: int = Field(ge=0, description="Estimated grams of protein.")
    carbs_g: int = Field(ge=0, description="Estimated grams of carbohydrate.")
    fat_g: int = Field(ge=0, description="Estimated grams of fat.")


class MealRecommendations(BaseModel):
    """The whole reply, as an object rather than a bare list so fields can be
    added later without changing its shape. ``min_length=1`` is one of the
    few constraints the API enforces itself."""

    suggestions: list[MealSuggestion] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Pure prompt construction (no network).
# ---------------------------------------------------------------------------

# Static, so every request shares it. (Too short for prompt caching to apply
# — the API only caches prefixes over a model-dependent minimum length.)
SYSTEM_PROMPT = """\
You suggest meal ideas for FitTrack, a calorie and macronutrient tracking app. \
You'll be given how much of the user's daily budget is left today, and \
sometimes which meal they're planning.

Suggest everyday meals: common foods and simple dishes someone could \
realistically make or order. Each suggestion's estimated nutrition should fit \
within the remaining amounts. When a meal is named, size the suggestions as a \
sensible portion of that meal; a snack or breakfast shouldn't try to use up a \
large remaining budget on its own. Make the suggestions meaningfully different \
from one another.

The nutrition figures are estimates, so describe the portion they assume. \
These are general meal ideas, not nutrition or medical advice: don't \
diagnose, prescribe diets, make health claims, or comment on the user's body \
or goals."""


def _whole(value: float) -> int:
    """Round to a whole number, floored at zero."""
    return max(0, round(value))


def build_meal_prompt(request: MealRequest) -> str:
    """The user turn: today's remaining budget, the meal, and how many ideas.

    Values are rounded (Claude doesn't need fractions of a gram) and clamped
    at zero: someone who is over on a macro has none of it left, and a
    negative budget would only confuse the model. Whether to ask at all once
    the budget is spent is the caller's decision, not this function's.
    """
    r = request.remaining
    # `.value`, not the member itself: on Python 3.12+ an f-string of a
    # str-mixin Enum renders "MealType.DINNER", not "dinner".
    meal = request.meal_type.value if request.meal_type else "any meal"
    return (
        "Remaining budget for today:\n"
        f"- Calories: {_whole(r.calories)} kcal\n"
        f"- Protein: {_whole(r.protein_g)} g\n"
        f"- Carbs: {_whole(r.carbs_g)} g\n"
        f"- Fat: {_whole(r.fat_g)} g\n"
        "\n"
        f"Meal: {meal}\n"
        f"Suggest {request.count} meal ideas."
    )


# ---------------------------------------------------------------------------
# The SDK call.
# ---------------------------------------------------------------------------

# Room for adaptive thinking plus the JSON reply. A ceiling, not a target —
# only generated tokens are billed — and generous on purpose: a reply cut off
# mid-JSON fails validation and wastes the whole call. The timeout, not this,
# bounds how long a user waits.
_MAX_TOKENS = 16_000


def _api_key() -> str | None:
    """The configured key, or ``None``. An empty ``ANTHROPIC_API_KEY=`` line
    in ``.env`` counts as unset rather than as a key that will fail with 401."""
    key = settings.anthropic_api_key
    return (key.get_secret_value() or None) if key is not None else None


def is_enabled() -> bool:
    """Whether AI features are switched on *and* have a key to call with.

    Lets a caller tell "not set up" apart from "temporarily failing", the way
    ``FoodSearchResponse.external`` distinguishes OFF's disabled/unavailable.
    """
    return settings.ai_enabled and _api_key() is not None


def _client(
    client: anthropic.Anthropic | None,
) -> tuple[anthropic.Anthropic, bool]:
    """Return the client to use and whether we own it (and must close it).

    Tests inject a client backed by a mock transport; production builds a
    short-lived one per call, like ``off_client`` (a connection handshake is
    noise next to a multi-second generation). The key is passed explicitly:
    pydantic-settings reads ``.env`` into ``settings`` without exporting it
    to the process environment, which is where the SDK would look.
    """
    if client is not None:
        return client, False
    made = anthropic.Anthropic(
        api_key=_api_key(),
        timeout=settings.ai_timeout_seconds,
        max_retries=settings.ai_max_retries,
    )
    return made, True


def _call[T: BaseModel](
    client: anthropic.Anthropic | None,
    *,
    system: str,
    content: str | list[dict],
    output_format: type[T],
) -> T:
    """One structured Claude request, shared by every AI feature.

    Owns everything that isn't feature-specific: the on/off check, the
    client's lifecycle, the model/effort/thinking settings, and turning every
    failure into :class:`AiUnavailableError`. Returns the validated
    ``output_format`` instance.
    """
    if not is_enabled():
        raise AiUnavailableError("AI features are switched off or have no key")

    cli, owns = _client(client)
    try:
        response = cli.messages.parse(
            model=settings.ai_model,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": content}],
            thinking={"type": "adaptive"},
            output_config={"effort": settings.ai_effort},
            output_format=output_format,
        )
    except (
        anthropic.AuthenticationError,
        anthropic.PermissionDeniedError,
        anthropic.NotFoundError,
        anthropic.BadRequestError,
    ) as exc:
        # Misconfiguration — a bad key, an unknown AI_MODEL, a parameter this
        # model rejects. It won't fix itself, so log it loudly; to the user
        # it's the same "unavailable" as an outage.
        logger.error(
            "Claude rejected the request (HTTP %s, request_id=%s): %s",
            exc.status_code,
            exc.request_id,
            exc.message,
        )
        raise AiUnavailableError(
            f"Claude rejected the request ({exc.status_code})"
        ) from exc
    except anthropic.APIError as exc:
        # Transient — rate limit, overload, 5xx, timeout, network. The SDK has
        # already retried (``ai_max_retries``) by the time this surfaces.
        logger.warning("Claude unavailable: %s", exc)
        raise AiUnavailableError("Claude is unavailable") from exc
    except pydantic.ValidationError as exc:
        # parse() validates inside the call, so a reply that doesn't match the
        # schema — cut off mid-JSON, a refusal's prose, a negative calorie
        # count — raises here rather than coming back as a None result.
        logger.warning("Claude's reply failed validation: %s", exc)
        raise AiUnavailableError("Claude returned an unusable reply") from exc
    finally:
        if owns:
            cli.close()

    result = response.parsed_output
    if response.stop_reason != "end_turn" or result is None:
        # e.g. a refusal that produced no text to validate.
        raise AiUnavailableError(
            f"Claude did not finish (stop_reason={response.stop_reason})"
        )
    return result


def recommend_meals(
    request: MealRequest, *, client: anthropic.Anthropic | None = None
) -> list[MealSuggestion]:
    """Ask Claude for meal ideas that fit ``request``'s remaining budget.

    Returns at most ``request.count`` validated suggestions. Raises
    :class:`AiUnavailableError` if the feature is off or unconfigured, or if
    the call fails in any way.
    """
    result = _call(
        client,
        system=SYSTEM_PROMPT,
        content=build_meal_prompt(request),
        output_format=MealRecommendations,
    )
    # The count is asked for in the prompt but can't be a schema rule (the API
    # doesn't enforce maximums), so trim extras rather than reject a good reply.
    return result.suggestions[: request.count]


# ---------------------------------------------------------------------------
# Photo calorie estimation.
# ---------------------------------------------------------------------------

# Comfortably under the API's per-image limit even counting base64's ~4/3
# growth. The browser downscales to ~1568 px JPEG (a few hundred KB) first, so
# only something bypassing the UI gets near this.
MAX_IMAGE_BYTES = 3 * 1024 * 1024

# A plate rarely holds more than a handful of distinct things; the cap stops
# a cluttered photo from producing an unreviewable list.
MAX_PHOTO_ITEMS = 10

# The formats Claude accepts, identified by their leading "magic" bytes
# rather than by the client's claimed content type or file extension.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def sniff_image_type(data: bytes) -> str | None:
    """The media type of ``data`` if it's an image format Claude accepts
    (JPEG, PNG, GIF, WebP), judged by its magic bytes; otherwise ``None``.

    A client's ``Content-Type`` is just a claim — this checks the bytes.
    """
    for signature, media_type in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return media_type
    # WebP is a RIFF container: "RIFF", a 4-byte size, then "WEBP".
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class EstimatedItem(BaseModel):
    """One food or drink Claude sees in the photo.

    Nutrition is *per 100 g* (the app's canonical form) plus an estimated
    weight: the portion is the uncertain part of a photo estimate, so the
    user corrects the grams and every figure rescales by one multiplication.
    The bounds are physical — pure fat is 900 kcal/100 g, and no macro can
    exceed 100 g per 100 g.
    """

    name: str = Field(description="What it is, e.g. 'Grilled chicken breast'.")
    grams: int = Field(
        ge=1, le=5000, description="Estimated weight of this item as served."
    )
    calories_per_100g: float = Field(
        ge=0, le=900, description="Typical kcal per 100 g, as prepared."
    )
    protein_per_100g: float = Field(ge=0, le=100, description="Grams per 100 g.")
    carbs_per_100g: float = Field(ge=0, le=100, description="Grams per 100 g.")
    fat_per_100g: float = Field(ge=0, le=100, description="Grams per 100 g.")


class PhotoEstimate(BaseModel):
    """Claude's reading of a meal photo. ``items`` is empty when there's no
    food in the photo; ``note`` then says so."""

    items: list[EstimatedItem] = Field(
        description="Each distinct food or drink visible; empty if none."
    )
    confidence: Literal["low", "medium", "high"] = Field(
        description="How reliable the portion estimates are, given the photo."
    )
    note: str = Field(
        description="One short sentence for the user: the main assumption "
        "made (e.g. cooking oil, hidden fillings), or that no food is visible."
    )


PHOTO_SYSTEM_PROMPT = """\
You estimate the nutrition of food in photos for FitTrack, a calorie and \
macronutrient tracking app. The user will review and adjust your estimate \
before logging it, so aim for realistic typical values rather than cautious \
ones.

List each distinct food or drink you can see. Keep items that are eaten \
together and can't sensibly be separated as one item (a sandwich, a mixed \
salad, a bowl of soup). For each, estimate its weight in grams as served and \
its typical nutrition per 100 g as prepared, accounting for visible cooking \
methods, sauces and oils. Use the plate, utensils and packaging for scale.

If there is no food or drink in the photo, return no items and say so in the \
note. Describe only the food: don't comment on the person, their health or \
their diet, and don't give nutrition or medical advice."""

PHOTO_PROMPT = "Estimate the food in this photo."


def estimate_photo(
    image: bytes, media_type: str, *, client: anthropic.Anthropic | None = None
) -> PhotoEstimate:
    """Ask Claude to identify the food in a photo and estimate its nutrition.

    ``image`` must already be validated by the caller (a type from
    :func:`sniff_image_type`, at most :data:`MAX_IMAGE_BYTES`). Returns the
    estimate with at most :data:`MAX_PHOTO_ITEMS` items. Raises
    :class:`AiUnavailableError` if the feature is off or the call fails.
    """
    estimate = _call(
        client,
        system=PHOTO_SYSTEM_PROMPT,
        # The image goes before the instruction, the order Claude handles best.
        content=[
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(image).decode("ascii"),
                },
            },
            {"type": "text", "text": PHOTO_PROMPT},
        ],
        output_format=PhotoEstimate,
    )
    estimate.items = estimate.items[:MAX_PHOTO_ITEMS]
    return estimate
