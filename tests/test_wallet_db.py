"""Wallet persistence tests (SQLite)."""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

# Must set DB URL before settings/engine are first used in this module's fixtures.
os.environ["LEBNE_DATABASE_URL"] = "sqlite:///./test_lebne_wallet.db"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_path = tmp_path / "wallet.db"
    monkeypatch.setenv("LEBNE_DATABASE_URL", f"sqlite:///{db_path}")
    from api.config import get_settings
    from wallet.db import init_db, reset_engine

    get_settings.cache_clear()
    reset_engine()
    init_db()
    yield
    reset_engine()
    get_settings.cache_clear()


def test_ledger_updates_balance_and_list():
    from api.config import get_settings
    from api.security.auth import decode_token, mint_access_token, principal_from_payload
    from wallet.service import wallet_service

    settings = get_settings()
    token = mint_access_token(user_id="u-ledger", roles=["end_user"], settings=settings)
    principal = principal_from_payload(decode_token(token, settings))

    posted = wallet_service.post_ledger_entry(
        principal,
        "u-ledger",
        amount_mru=1500,
        kind="topup",
        reference="cash-1",
        idempotency_key="idem-1",
    )
    assert posted["balance_mru"] == 1500

    replay = wallet_service.post_ledger_entry(
        principal,
        "u-ledger",
        amount_mru=1500,
        kind="topup",
        reference="cash-1",
        idempotency_key="idem-1",
    )
    assert replay["idempotent_replay"] is True
    assert replay["balance_mru"] == 1500

    bal = wallet_service.get_balance(principal, "u-ledger")
    assert bal["balance_mru"] == 1500

    tx = wallet_service.list_transactions(principal, "u-ledger")
    assert len(tx["transactions"]) == 1
    assert tx["transactions"][0]["amount_mru"] == 1500


def test_insufficient_balance():
    from api.config import get_settings
    from api.security.auth import decode_token, mint_access_token, principal_from_payload
    from wallet.service import wallet_service

    settings = get_settings()
    token = mint_access_token(user_id="u-poor", roles=["end_user"], settings=settings)
    principal = principal_from_payload(decode_token(token, settings))
    with pytest.raises(HTTPException):
        wallet_service.post_ledger_entry(
            principal,
            "u-poor",
            amount_mru=-10,
            kind="transfer_out",
        )
