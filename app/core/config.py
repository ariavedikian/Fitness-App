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

    # --- Open Food Facts (external nutrition database) ---
    # A free, open food database (millions of products, no API key). When
    # disabled, food search falls back to our local database only — handy for
    # tests and offline development so neither depends on a third party.
    off_enabled: bool = True
    off_base_url: str = "https://world.openfoodfacts.org"
    off_timeout_seconds: float = 6.0
    # Their public full-text search (`search.pl`) is intermittently throttled
    # and answers 503 at random even when healthy, so requests retry briefly
    # before giving up rather than surfacing a transient blip to the user.
    off_max_retries: int = 2
    off_retry_backoff_seconds: float = 0.25
    off_search_page_size: int = 20
    # OFF asks callers to send a descriptive User-Agent identifying the app.
    # Add a contact (email/URL) via .env if running this against their live
    # service in earnest; kept generic here so nothing personal is committed.
    off_user_agent: str = "FitTrack/0.1 (mentoring project)"

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
