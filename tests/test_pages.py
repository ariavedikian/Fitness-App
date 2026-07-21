"""Tests for the HTML page routes."""

import pytest
from fastapi.testclient import TestClient

SIGNUP = {"email": "lifter@example.com", "password": "correct-horse-battery"}


def sign_in(client: TestClient) -> None:
    client.post("/api/auth/register", json=SIGNUP)


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_auth_pages_render_for_anonymous_visitors(
    client: TestClient, path: str
) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_home_sends_anonymous_visitors_to_login(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_home_sends_signed_in_users_to_the_dashboard(client: TestClient) -> None:
    sign_in(client)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


def test_dashboard_sends_anonymous_visitors_to_login(client: TestClient) -> None:
    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_dashboard_renders_for_signed_in_users(client: TestClient) -> None:
    sign_in(client)

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert SIGNUP["email"] in response.text


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_auth_pages_send_signed_in_users_to_the_dashboard(
    client: TestClient, path: str
) -> None:
    sign_in(client)

    response = client.get(path, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/dashboard"


def test_profile_page_redirects_anonymous_visitors(client: TestClient) -> None:
    response = client.get("/profile", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_profile_page_renders_for_signed_in_users(client: TestClient) -> None:
    sign_in(client)

    response = client.get("/profile")

    assert response.status_code == 200
    assert "profile-form" in response.text


def test_foods_page_redirects_anonymous_visitors(client: TestClient) -> None:
    response = client.get("/foods", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_foods_page_renders_for_signed_in_users(client: TestClient) -> None:
    sign_in(client)

    response = client.get("/foods")

    assert response.status_code == 200
    assert "food-search" in response.text


def test_diary_page_redirects_anonymous_visitors(client: TestClient) -> None:
    response = client.get("/diary", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_diary_page_renders_for_signed_in_users(client: TestClient) -> None:
    sign_in(client)

    response = client.get("/diary")

    assert response.status_code == 200
    assert "diary-content" in response.text


def test_workouts_page_redirects_anonymous_visitors(client: TestClient) -> None:
    response = client.get("/workouts", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_workouts_page_renders_for_signed_in_users(client: TestClient) -> None:
    sign_in(client)

    response = client.get("/workouts")

    assert response.status_code == 200
    assert "exercise-search" in response.text


def test_progress_page_redirects_anonymous_visitors(client: TestClient) -> None:
    response = client.get("/progress", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_progress_page_renders_for_signed_in_users(client: TestClient) -> None:
    sign_in(client)

    response = client.get("/progress")

    assert response.status_code == 200
    assert "weight-form" in response.text


def test_analytics_page_redirects_anonymous_visitors(client: TestClient) -> None:
    response = client.get("/analytics", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_analytics_page_renders_for_signed_in_users(client: TestClient) -> None:
    sign_in(client)

    response = client.get("/analytics")

    assert response.status_code == 200
    assert "range-select" in response.text


def test_pages_are_absent_from_the_api_schema(client: TestClient) -> None:
    # /docs should describe the API, not the website.
    paths = client.get("/openapi.json").json()["paths"]

    assert "/dashboard" not in paths
    assert "/api/auth/login" in paths
