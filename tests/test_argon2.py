"""Argon2 + local auth tests."""

from __future__ import annotations

import pytest

from api.config import get_settings
from wallet.db import init_db, reset_engine
from wallet.passwords import hash_password, verify_password
from wallet.service import wallet_service


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("LEBNE_DATABASE_URL", f"sqlite:///{tmp_path / 'argon.db'}")
    monkeypatch.setenv("LEBNE_EMBEDDING_BACKEND", "hash")
    get_settings.cache_clear()
    reset_engine()
    init_db()
    yield
    reset_engine()
    get_settings.cache_clear()


def test_argon2_hash_verify():
    h = hash_password("CorrectHorse1")
    assert h.startswith("$argon2")
    assert verify_password(h, "CorrectHorse1")
    assert not verify_password(h, "wrong-password")


def test_wallet_password_roundtrip():
    from api.security.auth import decode_token, mint_access_token, principal_from_payload

    settings = get_settings()
    wallet_service.ensure_user_with_password("u-argon", "CorrectHorse1")
    assert wallet_service.verify_user_password("u-argon", "CorrectHorse1")
    assert not wallet_service.verify_user_password("u-argon", "nope-nope")

    token = mint_access_token(user_id="u-argon", settings=settings)
    principal = principal_from_payload(decode_token(token, settings))
    wallet_service.change_password(principal, "u-argon", "NewPassword9")
    assert wallet_service.verify_user_password("u-argon", "NewPassword9")
