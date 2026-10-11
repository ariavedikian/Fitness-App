"""Tests for serving /static: browsers must revalidate before reusing a file.

Without a Cache-Control header, browsers reused cached scripts without asking
for hours after they changed (see app/core/static.py).
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("path", ["/static/css/main.css", "/static/js/api.js"])
def test_static_files_must_be_revalidated(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    # The validator the browser sends back to ask "has it changed?".
    assert response.headers["etag"]


def test_an_unchanged_file_is_a_bodiless_304(client: TestClient) -> None:
    etag = client.get("/static/js/api.js").headers["etag"]

    response = client.get("/static/js/api.js", headers={"If-None-Match": etag})

    assert response.status_code == 304
    assert response.content == b""
    # Still marked, so the next use is revalidated too.
    assert response.headers["cache-control"] == "no-cache"


def test_a_stale_validator_gets_the_file(client: TestClient) -> None:
    response = client.get(
        "/static/js/api.js", headers={"If-None-Match": '"an-older-version"'}
    )

    assert response.status_code == 200
    assert b"apiFetch" in response.content
