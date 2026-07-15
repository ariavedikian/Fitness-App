"""Password hashing helpers.

Plaintext passwords exist only for the lifetime of a request: they are
hashed on arrival and never stored, logged, or returned.
"""

import bcrypt


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage.

    ``gensalt()`` generates a new random salt every call, so two users with
    the same password still get different hashes. The salt is stored inside
    the returned string, which is why ``verify_password`` needs no separate
    salt argument.
    """
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a stored hash.

    Hashing is one-way, so the check works by hashing the candidate with the
    stored salt and comparing; ``checkpw`` does that comparison in constant
    time to avoid leaking information through response timing.
    """
    return bcrypt.checkpw(
        password.encode("utf-8"), hashed_password.encode("utf-8")
    )
