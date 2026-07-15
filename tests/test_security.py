"""Tests for password hashing."""

from app.core.security import hash_password, verify_password

PASSWORD = "correct-horse-battery"


def test_hash_does_not_contain_the_password() -> None:
    assert PASSWORD not in hash_password(PASSWORD)


def test_verify_accepts_the_correct_password() -> None:
    assert verify_password(PASSWORD, hash_password(PASSWORD))


def test_verify_rejects_the_wrong_password() -> None:
    assert not verify_password("not-the-password", hash_password(PASSWORD))


def test_identical_passwords_get_different_hashes() -> None:
    # Each hash uses a fresh random salt, so a stolen database cannot be
    # scanned for users who share a password, and precomputed rainbow tables
    # are useless against it.
    assert hash_password(PASSWORD) != hash_password(PASSWORD)
