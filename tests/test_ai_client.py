"""Tests for the Claude integration (meal ideas, photo estimates, workouts).

Two halves, like ``test_off_client``:

* the **pure** half — prompt construction and the feature switch — is tested
  directly;
* the **SDK call** runs through a *real* ``anthropic.Anthropic`` client whose
  HTTP is answered by an ``httpx2.MockTransport``. No network and no real
  key, but the SDK's own request building and ``parse()`` validation still
  run — so a misspelled parameter or a schema the SDK can't send fails here,
  where a hand-rolled fake client would silently accept it.
"""

import base64
import json
import logging

import anthropic
import httpx2
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.models.log_entry import MealType
from app.services import ai_client
from app.services.ai_client import (
    MAX_PHOTO_ITEMS,
    MAX_WORKOUT_EXERCISES,
    PHOTO_PROMPT,
    PHOTO_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    WORKOUT_SYSTEM_PROMPT,
    AiUnavailableError,
    CatalogueExercise,
    EstimatedItem,
    MealRequest,
    MealSuggestion,
    PastWorkout,
    SuggestedExercise,
    WorkoutRequest,
    build_meal_prompt,
    build_workout_prompt,
    build_workout_schema,
    estimate_photo,
    is_enabled,
    recommend_meals,
    recommend_workout,
    sniff_image_type,
)
from app.services.nutrition import ActivityLevel, Goal, Nutrition
from app.services.workout import ExerciseType, WorkoutFocus

REQUEST = MealRequest(
    remaining=Nutrition(calories=850.4, protein_g=60.2, carbs_g=70.6, fat_g=25.0),
    meal_type=MealType.DINNER,
)

SUGGESTION = {
    "name": "Salmon rice bowl",
    "description": "150 g baked salmon over a cup of rice with greens.",
    "calories": 620,
    "protein_g": 42,
    "carbs_g": 60,
    "fat_g": 20,
}


def _message(text: str | None, *, stop_reason: str = "end_turn") -> dict:
    """A Messages API response body; ``text=None`` means no content blocks."""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": settings.ai_model,
        "content": [] if text is None else [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 120, "output_tokens": 80},
    }


def _reply(*suggestions: dict) -> dict:
    """A successful structured reply carrying ``suggestions``."""
    return _message(json.dumps({"suggestions": list(suggestions)}))


def _error(status: int, error_type: str) -> tuple[int, dict]:
    return status, {"type": "error", "error": {"type": error_type, "message": "x"}}


def _answer(body: dict, *, status: int = 200, seen: list | None = None):
    """A transport handler that answers every request with ``body``,
    recording each request in ``seen`` when given."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        if seen is not None:
            seen.append(request)
        return httpx2.Response(status, json=body)

    return handler


def _sdk(handler) -> anthropic.Anthropic:
    """A real SDK client whose HTTP is answered by ``handler``.

    ``max_retries=0`` keeps the failure tests instant (no backoff sleeps); the
    production retry setting is checked separately, on ``_client``.
    """
    return anthropic.Anthropic(
        api_key="sk-ant-test",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


# ---------------------------------------------------------------------------
# Pure: the prompt.
# ---------------------------------------------------------------------------


def test_prompt_states_rounded_budget_meal_and_count() -> None:
    assert build_meal_prompt(REQUEST) == (
        "Remaining budget for today:\n"
        "- Calories: 850 kcal\n"
        "- Protein: 60 g\n"
        "- Carbs: 71 g\n"  # 70.6 rounds up
        "- Fat: 25 g\n"
        "\n"
        "Meal: dinner\n"  # the enum's value, not "MealType.DINNER"
        "Suggest 3 meal ideas."
    )


def test_prompt_clamps_an_overspent_budget_to_zero() -> None:
    prompt = build_meal_prompt(
        MealRequest(
            remaining=Nutrition(calories=-150, protein_g=12, carbs_g=-3.4, fat_g=0)
        )
    )
    assert prompt.splitlines()[1:5] == [
        "- Calories: 0 kcal",
        "- Protein: 12 g",
        "- Carbs: 0 g",
        "- Fat: 0 g",
    ]


def test_prompt_without_a_meal_type_asks_for_any_meal() -> None:
    prompt = build_meal_prompt(
        MealRequest(remaining=Nutrition(calories=500), count=2)
    )
    assert "Meal: any meal" in prompt
    assert prompt.endswith("Suggest 2 meal ideas.")


# ---------------------------------------------------------------------------
# The feature switch.
# ---------------------------------------------------------------------------


def test_disabled_in_tests_by_default() -> None:
    assert not is_enabled()


@pytest.mark.parametrize("key", [None, ""])
def test_flag_without_a_usable_key_is_not_enabled(
    monkeypatch: pytest.MonkeyPatch, key: str | None
) -> None:
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(
        settings, "anthropic_api_key", None if key is None else SecretStr(key)
    )
    assert not is_enabled()


def test_enabled_with_flag_and_key(ai_on: None) -> None:
    assert is_enabled()


def test_production_client_is_configured_from_settings(ai_on: None) -> None:
    cli, owns = ai_client._client(None)
    try:
        assert owns  # we built it, so recommend_meals must close it
        assert cli.api_key == "sk-ant-test"
        assert cli.timeout == settings.ai_timeout_seconds
        assert cli.max_retries == settings.ai_max_retries
    finally:
        cli.close()


def test_api_key_is_masked_in_settings_repr(ai_on: None) -> None:
    assert "sk-ant-test" not in repr(settings)


# ---------------------------------------------------------------------------
# The SDK call: success.
# ---------------------------------------------------------------------------


def test_returns_validated_suggestions(ai_on: None) -> None:
    result = recommend_meals(REQUEST, client=_sdk(_answer(_reply(SUGGESTION))))
    assert result == [MealSuggestion(**SUGGESTION)]


def test_sends_the_configured_request(ai_on: None) -> None:
    seen: list[httpx2.Request] = []
    recommend_meals(REQUEST, client=_sdk(_answer(_reply(SUGGESTION), seen=seen)))

    (request,) = seen
    assert request.url.path == "/v1/messages"
    body = json.loads(request.content)
    assert body["model"] == settings.ai_model
    assert body["system"] == SYSTEM_PROMPT
    assert body["messages"] == [
        {"role": "user", "content": build_meal_prompt(REQUEST)}
    ]
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"]["effort"] == settings.ai_effort

    # parse() turned the Pydantic model into a JSON-schema output format,
    # merged alongside our effort setting.
    fmt = body["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["required"] == ["suggestions"]
    # ge=0 isn't enforceable by the API, so the SDK sends it as a hint.
    calories = fmt["schema"]["$defs"]["MealSuggestion"]["properties"]["calories"]
    assert "minimum: 0" in calories["description"]


def test_trims_extra_suggestions_to_the_requested_count(ai_on: None) -> None:
    request = MealRequest(remaining=REQUEST.remaining, count=2)
    reply = _reply(*({**SUGGESTION, "name": f"Idea {i}"} for i in range(4)))

    result = recommend_meals(request, client=_sdk(_answer(reply)))

    assert [s.name for s in result] == ["Idea 0", "Idea 1"]


# ---------------------------------------------------------------------------
# The SDK call: every failure degrades to AiUnavailableError.
# ---------------------------------------------------------------------------


def test_disabled_raises_without_calling_claude() -> None:
    seen: list[httpx2.Request] = []
    with pytest.raises(AiUnavailableError):
        recommend_meals(REQUEST, client=_sdk(_answer(_reply(SUGGESTION), seen=seen)))
    assert seen == []


@pytest.mark.parametrize(
    "status, error_type",
    [(429, "rate_limit_error"), (500, "api_error"), (529, "overloaded_error")],
)
def test_transient_api_errors_become_unavailable(
    ai_on: None, status: int, error_type: str
) -> None:
    status, body = _error(status, error_type)
    with pytest.raises(AiUnavailableError):
        recommend_meals(REQUEST, client=_sdk(_answer(body, status=status)))


def test_a_rejected_key_is_logged_as_an_error(
    ai_on: None, caplog: pytest.LogCaptureFixture
) -> None:
    # A bad key won't fix itself, so it must be loud in the logs even though
    # the user just sees "unavailable".
    status, body = _error(401, "authentication_error")
    with caplog.at_level(logging.ERROR, logger=ai_client.__name__):
        with pytest.raises(AiUnavailableError):
            recommend_meals(REQUEST, client=_sdk(_answer(body, status=status)))
    assert "HTTP 401" in caplog.text


def test_network_failure_becomes_unavailable(ai_on: None) -> None:
    def unreachable(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(AiUnavailableError):
        recommend_meals(REQUEST, client=_sdk(unreachable))


def test_refusal_becomes_unavailable(ai_on: None) -> None:
    refusal = _message(None, stop_reason="refusal")
    with pytest.raises(AiUnavailableError, match="refusal"):
        recommend_meals(REQUEST, client=_sdk(_answer(refusal)))


def test_reply_cut_off_mid_json_becomes_unavailable(ai_on: None) -> None:
    truncated = _message('{"suggestions": [{"name": "Salm', stop_reason="max_tokens")
    # parse() validates inside the call, so this raises before stop_reason
    # is ever checked — it must be caught as a validation failure.
    with pytest.raises(AiUnavailableError, match="unusable reply"):
        recommend_meals(REQUEST, client=_sdk(_answer(truncated)))


def test_out_of_range_estimate_is_rejected(ai_on: None) -> None:
    # The API can't enforce ge=0; the SDK's validation against our model does.
    reply = _reply({**SUGGESTION, "calories": -50})
    with pytest.raises(AiUnavailableError, match="unusable reply"):
        recommend_meals(REQUEST, client=_sdk(_answer(reply)))


# ---------------------------------------------------------------------------
# Photo estimation: image sniffing (pure).
# ---------------------------------------------------------------------------

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32  # enough of a JPEG for the sniffer


@pytest.mark.parametrize(
    "data, expected",
    [
        (JPEG, "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "image/png"),
        (b"GIF87a...", "image/gif"),
        (b"GIF89a...", "image/gif"),
        (b"RIFF\x24\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"RIFF\x24\x00\x00\x00WAVEfmt ", None),  # RIFF, but audio
        (b"\x00\x00\x00\x18ftypheic", None),  # HEIC: Claude can't read it
        (b"%PDF-1.7", None),
        (b"", None),
    ],
)
def test_sniffs_image_type_from_magic_bytes(
    data: bytes, expected: str | None
) -> None:
    assert sniff_image_type(data) == expected


# ---------------------------------------------------------------------------
# Photo estimation: the SDK call.
# ---------------------------------------------------------------------------

RICE = {
    "name": "Steamed white rice",
    "grams": 180,
    "calories_per_100g": 130,
    "protein_per_100g": 2.7,
    "carbs_per_100g": 28.2,
    "fat_per_100g": 0.3,
}


def _photo_reply(*items: dict, confidence: str = "medium") -> dict:
    estimate = {
        "items": list(items),
        "confidence": confidence,
        "note": "Assumed no oil.",
    }
    return _message(json.dumps(estimate))


def test_estimate_returns_validated_items(ai_on: None) -> None:
    estimate = estimate_photo(
        JPEG, "image/jpeg", client=_sdk(_answer(_photo_reply(RICE)))
    )

    assert estimate.items == [EstimatedItem(**RICE)]
    assert (estimate.confidence, estimate.note) == ("medium", "Assumed no oil.")


def test_estimate_sends_the_image_before_the_instruction(ai_on: None) -> None:
    seen: list[httpx2.Request] = []
    estimate_photo(
        JPEG, "image/jpeg", client=_sdk(_answer(_photo_reply(RICE), seen=seen))
    )

    body = json.loads(seen[0].content)
    assert body["system"] == PHOTO_SYSTEM_PROMPT
    image, text = body["messages"][0]["content"]
    assert image == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(JPEG).decode("ascii"),
        },
    }
    assert text == {"type": "text", "text": PHOTO_PROMPT}
    schema = body["output_config"]["format"]["schema"]
    assert set(schema["required"]) == {"items", "confidence", "note"}


def test_a_photo_without_food_is_an_empty_estimate(ai_on: None) -> None:
    reply = _message(
        json.dumps({"items": [], "confidence": "high", "note": "No food visible."})
    )

    estimate = estimate_photo(JPEG, "image/jpeg", client=_sdk(_answer(reply)))

    assert estimate.items == []
    assert estimate.note == "No food visible."


def test_estimate_caps_the_number_of_items(ai_on: None) -> None:
    many = [{**RICE, "name": f"Item {i}"} for i in range(MAX_PHOTO_ITEMS + 3)]

    estimate = estimate_photo(
        JPEG, "image/jpeg", client=_sdk(_answer(_photo_reply(*many)))
    )

    assert len(estimate.items) == MAX_PHOTO_ITEMS


def test_physically_impossible_nutrition_is_rejected(ai_on: None) -> None:
    # Over 900 kcal per 100 g is more than pure fat: a broken estimate.
    reply = _photo_reply({**RICE, "calories_per_100g": 950})
    with pytest.raises(AiUnavailableError, match="unusable reply"):
        estimate_photo(JPEG, "image/jpeg", client=_sdk(_answer(reply)))


def test_estimate_is_unavailable_when_ai_is_off() -> None:
    seen: list[httpx2.Request] = []
    with pytest.raises(AiUnavailableError):
        estimate_photo(
            JPEG, "image/jpeg", client=_sdk(_answer(_photo_reply(RICE), seen=seen))
        )
    assert seen == []


# ---------------------------------------------------------------------------
# Workout suggestions: the prompt and the catalogue-built schema (pure).
# ---------------------------------------------------------------------------

CARDIO, STRENGTH = ExerciseType.CARDIO, ExerciseType.STRENGTH

CATALOGUE = (
    CatalogueExercise("Running", CARDIO),
    CatalogueExercise("Walking", CARDIO),
    CatalogueExercise("Bench Press", STRENGTH, "Chest"),
    CatalogueExercise("Squat", STRENGTH, "Legs"),
    CatalogueExercise("Lunge", STRENGTH, "Legs"),
)

WORKOUT_REQUEST = WorkoutRequest(
    minutes=30,
    focus=WorkoutFocus.ANY,
    catalogue=CATALOGUE,
    history=(
        PastWorkout(0, "Running", CARDIO, minutes=29.6),
        PastWorkout(2, "Squat", STRENGTH, "Legs", sets=3, reps=8),
        PastWorkout(2, "Lunge", STRENGTH, "Legs", sets=3, reps=10),
    ),
    goal=Goal.LOSE,
    activity_level=ActivityLevel.VERY_ACTIVE,
)


def test_workout_prompt_lists_catalogue_history_and_request() -> None:
    assert build_workout_prompt(WORKOUT_REQUEST) == (
        "Exercises to choose from:\n"
        "- Cardio: Running, Walking\n"
        "- Strength (Chest): Bench Press\n"  # groups sorted by name
        "- Strength (Legs): Squat, Lunge\n"
        "\n"
        "My recent workouts:\n"
        "- Today: Running 30 min (cardio)\n"  # 29.6 rounds up
        "- 2 days ago: Squat 3×8 (Legs); Lunge 3×10 (Legs)\n"
        "\n"
        "Goal: lose weight\n"
        "Activity level: very active\n"  # the value, underscore spelled out
        "Session length: 30 minutes\n"
        "Focus: any (balance it against my recent workouts)\n"
        "\n"
        "Suggest one workout for today."
    )


def test_workout_prompt_without_a_profile_or_history() -> None:
    prompt = build_workout_prompt(
        WorkoutRequest(minutes=15, focus=WorkoutFocus.CARDIO, catalogue=CATALOGUE)
    )
    assert "My recent workouts:\n- None logged." in prompt
    assert "Goal: not set\nActivity level: not set" in prompt
    assert "Focus: cardio" in prompt


def test_workout_schema_needs_a_catalogue() -> None:
    with pytest.raises(ValueError, match="empty catalogue"):
        build_workout_schema(())


# ---------------------------------------------------------------------------
# Workout suggestions: the SDK call.
# ---------------------------------------------------------------------------

WARM_UP = {"exercise": "Walking", "minutes": 5, "note": "Easy pace."}
BENCH = {"exercise": "Bench Press", "sets": 3, "reps": 10, "note": ""}


def _workout_reply(*exercises: dict) -> dict:
    plan = {
        "title": "Upper-body strength",
        "summary": "Your legs worked two days ago, so this trains the chest.",
        "exercises": list(exercises),
    }
    return _message(json.dumps(plan))


def _sent_schema(catalogue: tuple[CatalogueExercise, ...], reply: dict) -> dict:
    """The output schema the SDK actually sent for ``catalogue`` — what the
    API's constrained decoding works from."""
    seen: list[httpx2.Request] = []
    request = WorkoutRequest(minutes=30, focus=WorkoutFocus.ANY, catalogue=catalogue)
    recommend_workout(request, client=_sdk(_answer(reply, seen=seen)))
    return json.loads(seen[0].content)["output_config"]["format"]["schema"]


def _names_by_variant(schema: dict) -> dict[str, list[str]]:
    return {
        name: variant["properties"]["exercise"]["enum"]
        for name, variant in schema["$defs"].items()
    }


def test_schema_allows_only_catalogue_names_by_type(ai_on: None) -> None:
    schema = _sent_schema(CATALOGUE, _workout_reply(BENCH))

    assert _names_by_variant(schema) == {
        "StrengthExercise": ["Bench Press", "Squat", "Lunge"],
        "CardioExercise": ["Running", "Walking"],
    }
    # Each type carries its own metrics, so a cardio item can't have sets.
    required = {name: v["required"] for name, v in schema["$defs"].items()}
    assert required == {
        "StrengthExercise": ["exercise", "sets", "reps", "note"],
        "CardioExercise": ["exercise", "minutes", "note"],
    }


def test_schema_sends_an_enum_even_for_a_single_name(ai_on: None) -> None:
    # Pydantic emits a one-value Literal as `const`, which the SDK can't send
    # (it would become a description hint): it must still arrive as an enum.
    run = {"exercise": "Running", "minutes": 20, "note": ""}
    schema = _sent_schema(
        (CatalogueExercise("Running", CARDIO),), _workout_reply(run)
    )
    assert _names_by_variant(schema) == {"CardioExercise": ["Running"]}


def test_returns_a_validated_workout(ai_on: None) -> None:
    reply = _workout_reply(WARM_UP, BENCH)

    workout = recommend_workout(WORKOUT_REQUEST, client=_sdk(_answer(reply)))

    assert workout.title == "Upper-body strength"
    assert workout.summary.startswith("Your legs worked")
    # The type comes from our catalogue; the other type's metrics are None.
    assert workout.exercises == (
        SuggestedExercise("Walking", CARDIO, None, None, 5, "Easy pace."),
        SuggestedExercise("Bench Press", STRENGTH, 3, 10, None, ""),
    )


def test_sends_the_workout_request(ai_on: None) -> None:
    seen: list[httpx2.Request] = []
    recommend_workout(
        WORKOUT_REQUEST, client=_sdk(_answer(_workout_reply(BENCH), seen=seen))
    )

    body = json.loads(seen[0].content)
    assert body["system"] == WORKOUT_SYSTEM_PROMPT
    assert body["messages"] == [
        {"role": "user", "content": build_workout_prompt(WORKOUT_REQUEST)}
    ]
    assert body["output_config"]["format"]["schema"]["required"] == [
        "title",
        "summary",
        "exercises",
    ]


def test_trims_a_long_workout(ai_on: None) -> None:
    reply = _workout_reply(*[BENCH] * (MAX_WORKOUT_EXERCISES + 2))

    workout = recommend_workout(WORKOUT_REQUEST, client=_sdk(_answer(reply)))

    assert len(workout.exercises) == MAX_WORKOUT_EXERCISES


@pytest.mark.parametrize(
    "item",
    [
        # Not in the catalogue. The API's grammar can't produce this; the
        # SDK's validation against the same schema is the second guard.
        {"exercise": "Burpees", "sets": 3, "reps": 10, "note": ""},
        # A cardio exercise given strength metrics matches neither variant.
        {"exercise": "Running", "sets": 3, "reps": 10, "note": ""},
        # Outside the physical bounds.
        {**BENCH, "sets": 0},
    ],
    ids=["unknown-exercise", "wrong-metrics", "zero-sets"],
)
def test_an_invalid_exercise_makes_the_reply_unusable(
    ai_on: None, item: dict
) -> None:
    reply = _workout_reply(WARM_UP, item)
    with pytest.raises(AiUnavailableError, match="unusable reply"):
        recommend_workout(WORKOUT_REQUEST, client=_sdk(_answer(reply)))


def test_workout_is_unavailable_when_ai_is_off() -> None:
    seen: list[httpx2.Request] = []
    with pytest.raises(AiUnavailableError):
        recommend_workout(
            WORKOUT_REQUEST, client=_sdk(_answer(_workout_reply(BENCH), seen=seen))
        )
    assert seen == []
