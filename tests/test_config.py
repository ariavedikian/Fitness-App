"""Tests for the settings guard on SECRET_KEY.

Outside debug mode the app must refuse to boot with a guessable session
secret: anyone who knows it can forge a login for any account. Settings are
built with ``_env_file=None`` so a developer's own ``.env`` can't leak in.
"""

import secrets

import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_SECRET_KEY, Settings


@pytest.mark.parametrize(
    "secret_key",
    [
        DEFAULT_SECRET_KEY,  # left unset
        "replace-me",  # an old placeholder, public on GitHub
        "",  # an empty `SECRET_KEY=` line
        "correct-horse-battery-staple",  # a password, not a random key (28)
    ],
    ids=["default", "placeholder", "empty", "short"],
)
def test_production_refuses_a_guessable_secret(secret_key: str) -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, debug=False, secret_key=secret_key)


def test_production_accepts_a_generated_secret() -> None:
    key = secrets.token_hex(32)  # what the error message tells you to run

    assert Settings(_env_file=None, debug=False, secret_key=key).secret_key == key


def test_debug_mode_runs_with_the_development_default() -> None:
    # Local development works out of the box, with no key to generate.
    assert Settings(_env_file=None, debug=True).secret_key == DEFAULT_SECRET_KEY
