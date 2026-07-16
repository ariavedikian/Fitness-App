"""Tests for the authentication endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models import User

VALID_SIGNUP = {"email": "lifter@example.com", "password": "correct-horse-battery"}


def test_register_creates_an_account(client: TestClient) -> None:
    response = client.post("/api/auth/register", json=VALID_SIGNUP)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == VALID_SIGNUP["email"]
    assert body["id"]
    assert body["created_at"]


def test_register_signs_the_new_user_in(client: TestClient) -> None:
    client.post("/api/auth/register", json=VALID_SIGNUP)

    # No separate login step: the session from registering is enough.
    assert client.get("/api/auth/me").status_code == 200


def test_register_never_returns_the_password(client: TestClient) -> None:
    response = client.post("/api/auth/register", json=VALID_SIGNUP)

    body = response.json()
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_stores_a_hash_not_the_password(
    client: TestClient, db: Session
) -> None:
    client.post("/api/auth/register", json=VALID_SIGNUP)

    user = db.scalars(
        select(User).where(User.email == VALID_SIGNUP["email"])
    ).one()
    assert user.hashed_password != VALID_SIGNUP["password"]
    assert verify_password(VALID_SIGNUP["password"], user.hashed_password)


def test_register_rejects_a_duplicate_email(client: TestClient) -> None:
    client.post("/api/auth/register", json=VALID_SIGNUP)

    response = client.post("/api/auth/register", json=VALID_SIGNUP)

    assert response.status_code == 409


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "not-an-email"),
        ("email", ""),
        ("password", "short"),
        ("password", "x" * 73),
    ],
)
def test_register_rejects_invalid_input(
    client: TestClient, field: str, value: str
) -> None:
    response = client.post(
        "/api/auth/register", json={**VALID_SIGNUP, field: value}
    )

    assert response.status_code == 422


def test_login_succeeds_with_correct_credentials(client: TestClient) -> None:
    client.post("/api/auth/register", json=VALID_SIGNUP)

    response = client.post("/api/auth/login", json=VALID_SIGNUP)

    assert response.status_code == 200
    assert response.json()["email"] == VALID_SIGNUP["email"]
    assert "fittrack_session" in response.cookies


def test_session_cookie_is_not_readable_by_javascript(client: TestClient) -> None:
    client.post("/api/auth/register", json=VALID_SIGNUP)

    response = client.post("/api/auth/login", json=VALID_SIGNUP)

    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


def test_session_cookie_does_not_contain_the_email(client: TestClient) -> None:
    # The cookie is signed, not encrypted — anything placed in it is
    # readable by the client, so it must hold nothing but an opaque id.
    client.post("/api/auth/register", json=VALID_SIGNUP)

    response = client.post("/api/auth/login", json=VALID_SIGNUP)

    assert VALID_SIGNUP["email"] not in response.cookies["fittrack_session"]


@pytest.mark.parametrize(
    "credentials",
    [
        {"email": VALID_SIGNUP["email"], "password": "wrong-password"},
        {"email": "nobody@example.com", "password": VALID_SIGNUP["password"]},
    ],
    ids=["wrong password", "unknown email"],
)
def test_login_rejects_bad_credentials(
    client: TestClient, credentials: dict[str, str]
) -> None:
    client.post("/api/auth/register", json=VALID_SIGNUP)

    response = client.post("/api/auth/login", json=credentials)

    assert response.status_code == 401
    # Identical wording either way, so the response cannot be used to
    # discover which emails are registered.
    assert response.json()["detail"] == "Incorrect email or password."
    assert "fittrack_session" not in response.cookies


def test_me_returns_the_signed_in_user(client: TestClient) -> None:
    client.post("/api/auth/register", json=VALID_SIGNUP)
    client.post("/api/auth/login", json=VALID_SIGNUP)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == VALID_SIGNUP["email"]


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_rejects_a_forged_session_cookie(client: TestClient) -> None:
    client.post("/api/auth/register", json=VALID_SIGNUP)
    client.cookies.set("fittrack_session", "not-a-validly-signed-value")

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_logout_ends_the_session(client: TestClient) -> None:
    client.post("/api/auth/register", json=VALID_SIGNUP)
    client.post("/api/auth/login", json=VALID_SIGNUP)

    logout = client.post("/api/auth/logout")

    assert logout.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
