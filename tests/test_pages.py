"""Tests for the HTML page routes."""

import re

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


def test_dashboard_offers_meal_ideas_when_ai_is_on(
    client: TestClient, ai_on: None
) -> None:
    sign_in(client)

    html = client.get("/dashboard").text

    assert "data-suggest" in html
    assert "/static/js/suggestions.js" in html


def test_foods_page_offers_photo_estimates_when_ai_is_on(
    client: TestClient, ai_on: None
) -> None:
    sign_in(client)

    html = client.get("/foods").text

    assert "data-photo" in html
    assert 'id="photo-dialog"' in html
    assert "/static/js/photo-estimate.js" in html


def test_foods_page_hides_photo_estimates_when_ai_is_off(
    client: TestClient,
) -> None:
    sign_in(client)

    html = client.get("/foods").text

    assert "data-photo" not in html
    assert "photo-estimate.js" not in html


def test_dashboard_hides_meal_ideas_when_ai_is_off(client: TestClient) -> None:
    # No dead button, and the script isn't even loaded.
    sign_in(client)

    html = client.get("/dashboard").text

    assert "data-suggest" not in html
    assert "suggestions.js" not in html


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


# ---------------------------------------------------------------- site nav
def _nav_links(html: str) -> list[str]:
    """Each site-nav link's opening tag, whitespace-collapsed."""
    return [
        " ".join(tag.split())
        for tag in re.findall(r'<a class="site-nav__link"[^>]*>', html)
    ]


@pytest.mark.parametrize("path", ["/dashboard", "/diary", "/analytics"])
def test_nav_marks_only_the_current_page(client: TestClient, path: str) -> None:
    sign_in(client)

    links = _nav_links(client.get(path).text)

    assert len(links) == 7
    current = [tag for tag in links if 'aria-current="page"' in tag]
    assert current == [f'<a class="site-nav__link" href="{path}" aria-current="page">']


def test_nav_has_an_accessible_menu_toggle(client: TestClient) -> None:
    sign_in(client)

    html = " ".join(client.get("/dashboard").text.split())

    # The button names what it controls and starts collapsed…
    assert 'aria-expanded="false" aria-controls="site-nav" data-nav-toggle' in html
    # …and the nav it controls is a labelled landmark.
    assert '<nav class="site-nav" id="site-nav" aria-label="Main">' in html
    assert "/static/js/nav.js" in html


def test_signed_out_pages_have_no_nav_or_menu(client: TestClient) -> None:
    html = client.get("/login").text

    assert "data-nav-toggle" not in html
    assert 'class="site-nav"' not in html
