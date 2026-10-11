"""Application configuration.

All runtime settings live here, loaded from environment variables (with a
local ``.env`` file for development). Code should import ``settings`` from
this module rather than reading ``os.environ`` directly, so every
configurable value has exactly one home.
"""

from pathlib import Path
from typing import Literal

from pydantic import PositiveInt, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolves to the project root regardless of where the server is started
# from: app/core/config.py -> app/core -> app -> project root.
BASE_DIR = Path(__file__).resolve().parents[2]

DEFAULT_SECRET_KEY = "dev-only-insecure-secret"

# A real key is random and long (``secrets.token_hex(32)`` gives 64
# characters). Anything shorter outside debug is a placeholder, an empty
# ``SECRET_KEY=`` line or a typed-in password — all guessable.
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    app_name: str = "FitTrack"
    debug: bool = False

    # SQLAlchemy connection string. Migrating to PostgreSQL later means
    # overriding this in .env — no code changes anywhere else.
    database_url: str = f"sqlite:///{(BASE_DIR / 'fittrack.db').as_posix()}"

    # Signs session cookies. Anyone who knows this value can forge a login
    # for any account, so the development default — or any short value — is
    # rejected outside debug mode by the validator below.
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

    # --- Claude (AI meal ideas, photo estimates, workout ideas) ---
    # Off by default: unlike OFF, every request is billed to an Anthropic
    # account, so the feature is opt-in. The flag doubles as a kill switch —
    # switch it off (e.g. during a cost spike) without removing the key.
    ai_enabled: bool = False
    # Read from ANTHROPIC_API_KEY — the same variable the SDK itself uses.
    # SecretStr keeps a billable credential out of reprs, logs and tracebacks.
    anthropic_api_key: SecretStr | None = None
    ai_model: str = "claude-opus-4-8"
    # How hard Claude thinks before answering: the main cost/latency dial.
    ai_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    # The SDK defaults (10 min, 2 retries) suit batch jobs, not a page someone
    # is waiting on; a timed-out attempt is also retried, so these multiply.
    ai_timeout_seconds: float = 60.0
    ai_max_retries: int = 1
    # Billed AI requests each user may make per rolling 24 hours (all AI
    # features share it). Generous for real use — a few meals plus re-rolls —
    # while capping what one account can spend. Positive, so a typo fails at
    # boot rather than silently blocking (or breaking) every request.
    ai_daily_limit: PositiveInt = 20

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
    )

    @model_validator(mode="after")
    def reject_weak_secret_outside_debug(self) -> "Settings":
        if not self.debug and (
            self.secret_key == DEFAULT_SECRET_KEY
            or len(self.secret_key) < MIN_SECRET_KEY_LENGTH
        ):
            raise ValueError(
                "SECRET_KEY must be a random value of at least "
                f"{MIN_SECRET_KEY_LENGTH} characters when DEBUG is false. "
                "Generate one with: "
                'python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return self


settings = Settings()
