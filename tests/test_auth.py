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
