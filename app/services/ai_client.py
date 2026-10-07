"""Claude integration: AI meal suggestions that fit the day's remaining budget.

This module is the **adapter** that quarantines the Anthropic SDK, the way
``off_client`` quarantines Open Food Facts: nothing else in the app imports
``anthropic``. Callers hand it a :class:`MealRequest` (plain numbers the
server computed) and get back validated :class:`MealSuggestion` objects — or
an :class:`AiUnavailableError`.

Two halves:

* **pure** — :data:`SYSTEM_PROMPT`, :func:`build_meal_prompt` and the
  Pydantic result schema. No network, so tests pin them down directly.
* **the SDK call** — :func:`recommend_meals` uses ``client.messages.parse()``
  with that schema: Claude's reply is constrained to matching JSON and
  validated into Pydantic objects, so there is no hand-parsing.

Every failure — feature off, no key, API error, refusal, a reply that fails
validation — becomes :class:`AiUnavailableError`, so the caller can *degrade*
("suggestions unavailable") instead of breaking the page.

Only server-computed numbers and an enum reach the prompt — never text the
user typed — so there is no prompt-injection surface here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

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
    """Whether suggestions are switched on *and* have a key to call with.

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


def recommend_meals(
    request: MealRequest, *, client: anthropic.Anthropic | None = None
) -> list[MealSuggestion]:
    """Ask Claude for meal ideas that fit ``request``'s remaining budget.

    Returns at most ``request.count`` validated suggestions. Raises
    :class:`AiUnavailableError` if the feature is off or unconfigured, or if
    the call fails in any way.
    """
    if not is_enabled():
        raise AiUnavailableError("AI suggestions are switched off or have no key")

    cli, owns = _client(client)
    try:
        response = cli.messages.parse(
            model=settings.ai_model,
            max_tokens=_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_meal_prompt(request)}],
            thinking={"type": "adaptive"},
            output_config={"effort": settings.ai_effort},
            output_format=MealRecommendations,
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
        raise AiUnavailableError(f"Claude rejected the request ({exc.status_code})") from exc
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
    # The count is asked for in the prompt but can't be a schema rule (the API
    # doesn't enforce maximums), so trim extras rather than reject a good reply.
    return result.suggestions[: request.count]
