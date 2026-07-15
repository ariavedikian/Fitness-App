"""Application configuration.

All runtime settings live here, loaded from environment variables (with a
local ``.env`` file for development). Code should import ``settings`` from
this module rather than reading ``os.environ`` directly, so every
configurable value has exactly one home.
"""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolves to the project root regardless of where the server is started
# from: app/core/config.py -> app/core -> app -> project root.
BASE_DIR = Path(__file__).resolve().parents[2]

DEFAULT_SECRET_KEY = "dev-only-insecure-secret"


class Settings(BaseSettings):
    app_name: str = "FitTrack"
    debug: bool = False

    # SQLAlchemy connection string. Migrating to PostgreSQL later means
    # overriding this in .env — no code changes anywhere else.
    database_url: str = f"sqlite:///{(BASE_DIR / 'fittrack.db').as_posix()}"

    # Signs session cookies. Anyone who knows this value can forge a login
    # for any account, so the development default is rejected outside debug
    # mode by the validator below.
    secret_key: str = DEFAULT_SECRET_KEY

    # How long a login lasts before the user must sign in again.
    session_max_age_seconds: int = 60 * 60 * 24 * 14  # 14 days

    # Restricts the session cookie to HTTPS. Must be true in production;
    # false locally, because a secure cookie is never sent over plain HTTP
    # and login would appear to silently fail.
    session_https_only: bool = False

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )

    @model_validator(mode="after")
    def reject_default_secret_outside_debug(self) -> "Settings":
        if not self.debug and self.secret_key == DEFAULT_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set to a random value when DEBUG is false. "
                "Generate one with: "
                'python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return self


settings = Settings()
