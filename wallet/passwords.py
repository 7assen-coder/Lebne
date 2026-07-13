"""Argon2id password hashing — never store plaintext passwords."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Tuned for interactive login; adjust memory_cost for your host.
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password too short")
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash or password_hash.startswith("pending:"):
        return False
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(password_hash)
    except Exception:
        return True
