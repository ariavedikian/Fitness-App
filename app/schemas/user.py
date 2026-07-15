"""Pydantic schemas for user requests and responses.

Schemas are the app's boundary with the outside world: they define what
callers are allowed to send in, and what we are willing to send back.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# bcrypt silently ignores anything past 72 bytes of input, so a longer
# password would give a false sense of strength. Reject it instead.
BCRYPT_MAX_BYTES = 72


class UserCreate(BaseModel):
    """Incoming registration payload."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=BCRYPT_MAX_BYTES)

    @field_validator("password")
    @classmethod
    def password_must_fit_bcrypt(cls, value: str) -> str:
        # max_length above counts characters; bcrypt's limit is bytes, and a
        # non-ASCII character can cost several.
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(
                f"password must be at most {BCRYPT_MAX_BYTES} bytes long"
            )
        return value


class UserRead(BaseModel):
    """A user account as exposed by the API.

    Note what is absent: ``hashed_password``. Responses are built from this
    schema rather than from the ORM object, so a sensitive column cannot
    leak into JSON just because someone added it to the model.
    """

    # Allows Pydantic to read attributes off a SQLAlchemy object rather than
    # requiring a dict.
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    created_at: datetime
