from api.security.acl import ACTION_SENSITIVITY
from api.schemas import AccountActionType, Sensitivity
from api.security.auth import mint_access_token, principal_from_payload, decode_token
from api.config import get_settings
from api.security.step_up import issue_confirmation, verify_confirmation_token, verify_two_fa, verify_two_fa_token, peek_dev_2fa_code
from api.security.acl import Scope
from wallet.service import wallet_service
from wallet.db import init_db, reset_engine
from api.security.auth import Principal
from fastapi import HTTPException
import pytest


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("LEBNE_DATABASE_URL", f"sqlite:///{tmp_path / 'sec.db'}")
    get_settings.cache_clear()
    reset_engine()
    init_db()
    yield
    reset_engine()
    get_settings.cache_clear()


def test_password_requires_2fa():
    assert ACTION_SENSITIVITY[AccountActionType.CHANGE_PASSWORD] == Sensitivity.STRONG_2FA


def test_balance_is_authenticated():
    assert ACTION_SENSITIVITY[AccountActionType.GET_BALANCE] == Sensitivity.AUTHENTICATED


def test_jwt_principal_scopes():
    settings = get_settings()
    token = mint_access_token(user_id="u1", roles=["end_user"], settings=settings)
    payload = decode_token(token, settings)
    principal = principal_from_payload(payload)
    assert principal.user_id == "u1"
    assert principal.has_scope(Scope.CHAT)
    assert principal.has_scope(Scope.BALANCE_READ)


def test_confirmation_token_single_use():
    settings = get_settings()
    challenge = issue_confirmation(
        user_id="u1",
        action=AccountActionType.UPDATE_PROFILE,
        session_id="s1",
        settings=settings,
    )
    verify_confirmation_token(
        challenge.confirmation_token,
        user_id="u1",
        action=AccountActionType.UPDATE_PROFILE,
        session_id="s1",
        settings=settings,
    )
    with pytest.raises(HTTPException):
        verify_confirmation_token(
            challenge.confirmation_token,
            user_id="u1",
            action=AccountActionType.UPDATE_PROFILE,
            session_id="s1",
            settings=settings,
        )


def test_two_fa_flow_and_wallet_acl():
    settings = get_settings()
    challenge = issue_confirmation(
        user_id="u2",
        action=AccountActionType.CHANGE_PHONE,
        session_id="s2",
        settings=settings,
    )
    assert challenge.two_fa_required
    assert challenge.two_fa_challenge_id
    code = peek_dev_2fa_code(challenge.two_fa_challenge_id, settings)
    assert code
    two_fa_token = verify_two_fa(
        challenge_id=challenge.two_fa_challenge_id,
        code=code,
        user_id="u2",
        action=AccountActionType.CHANGE_PHONE,
        settings=settings,
    )
    verify_two_fa_token(
        two_fa_token,
        user_id="u2",
        action=AccountActionType.CHANGE_PHONE,
        settings=settings,
    )

    token = mint_access_token(user_id="u2", roles=["end_user"], settings=settings)
    principal = principal_from_payload(decode_token(token, settings))
    result = wallet_service.change_phone(principal, "u2", "+22212345678")
    assert result["status"] == "phone_updated"

    other = Principal(user_id="u3", roles=("end_user",), scopes=principal.scopes)
    with pytest.raises(HTTPException):
        wallet_service.get_balance(other, "u2")
