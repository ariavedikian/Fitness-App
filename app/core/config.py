"""Application configuration.

All runtime settings live here, loaded from environment variables (with a
local ``.env`` file for development). Code should import ``settings`` from
this module rather than reading ``os.environ`` directly, so every
configurable value has exactly one home.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolves to the project root regardless of where the server is started
# from: app/core/config.py -> app/core -> app -> project root.
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "FitTrack"
    debug: bool = False

    # SQLAlchemy connection string. Migrating to PostgreSQL later means
    # overriding this in .env — no code changes anywhere else.
    database_url: str = f"sqlite:///{(BASE_DIR / 'fittrack.db').as_posix()}"

    # Signs session cookies (from Milestone 2 on). The default is only
    # acceptable for local development; any real deployment must set
    # SECRET_KEY in the environment.
    secret_key: str = "dev-only-insecure-secret"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
