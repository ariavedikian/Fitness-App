"""Application entry point.

Exposes ``app`` for the ASGI server (uvicorn) and builds it through an app
factory so tests can construct fresh, isolated instances.
"""

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, health
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Fitness and nutrition tracking API",
        version="0.1.0",
    )

    # Stores the session in a cookie that is signed with SECRET_KEY, so the
    # browser cannot tamper with it, and marked HttpOnly, so page JavaScript
    # (including anything injected via XSS) cannot read it.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="fittrack_session",
        max_age=settings.session_max_age_seconds,
        https_only=settings.session_https_only,
        # "lax" still sends the cookie on normal navigation to the site but
        # withholds it from cross-site POSTs, which blocks basic CSRF.
        same_site="lax",
    )

    app.include_router(health.router)
    app.include_router(auth.router)

    return app


app = create_app()
