"""Tests for the Claude integration (AI meal suggestions).

Two halves, like ``test_off_client``:

* the **pure** half — prompt construction and the feature switch — is tested
  directly;
* the **SDK call** runs through a *real* ``anthropic.Anthropic`` client whose
  HTTP is answered by an ``httpx2.MockTransport``. No network and no real
  key, but the SDK's own request building and ``parse()`` validation still
  run — so a misspelled parameter or a schema the SDK can't send fails here,
  where a hand-rolled fake client would silently accept it.
"""

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
    SYSTEM_PROMPT,
    AiUnavailableError,
    MealRequest,
    MealSuggestion,
    build_meal_prompt,
    is_enabled,
    recommend_meals,
)
from app.services.nutrition import Nutrition

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


@pytest.fixture
def ai_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch the feature on with a fake key (conftest forces it off)."""
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("sk-ant-test"))


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
