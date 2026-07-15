"""Application entry point.

Exposes ``app`` for the ASGI server (uvicorn) and builds it through an app
factory so tests can construct fresh, isolated instances.
"""

from fastapi import FastAPI

from app.api import auth, health
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Fitness and nutrition tracking API",
        version="0.1.0",
    )

    app.include_router(health.router)
    app.include_router(auth.router)

    return app


app = create_app()
