"""HTTP surface for Flutter / clients — ACL enforced via JWT scopes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.security.auth import Principal, get_current_principal
from wallet.service import wallet_service

router = APIRouter(prefix="/wallet/v1", tags=["wallet"])


class ProfileUpdate(BaseModel):
    display_name: str | None = None


class PasswordChange(BaseModel):
    new_password: str = Field(min_length=8)


class PhoneChange(BaseModel):
    new_phone: str = Field(min_length=8)


class LedgerPost(BaseModel):
    amount_mru: int
    kind: str = Field(default="adjust", min_length=2)
    reference: str = ""
    note: str = ""
    idempotency_key: str | None = None


@router.get("/users/{user_id}/balance")
async def get_balance(user_id: str, principal: Principal = Depends(get_current_principal)):
    return wallet_service.get_balance(principal, user_id)


@router.get("/users/{user_id}/transactions")
async def list_transactions(user_id: str, principal: Principal = Depends(get_current_principal)):
    return wallet_service.list_transactions(principal, user_id)


@router.post("/users/{user_id}/profile")
async def update_profile(
    user_id: str,
    body: ProfileUpdate,
    principal: Principal = Depends(get_current_principal),
):
    return wallet_service.update_profile(principal, user_id, body.display_name)


@router.post("/users/{user_id}/password")
async def change_password(
    user_id: str,
    body: PasswordChange,
    principal: Principal = Depends(get_current_principal),
):
    return wallet_service.change_password(principal, user_id, body.new_password)


@router.post("/users/{user_id}/phone")
async def change_phone(
    user_id: str,
    body: PhoneChange,
    principal: Principal = Depends(get_current_principal),
):
    return wallet_service.change_phone(principal, user_id, body.new_phone)


@router.post("/users/{user_id}/ledger")
async def post_ledger(
    user_id: str,
    body: LedgerPost,
    principal: Principal = Depends(get_current_principal),
):
    """Dev/ops credit-debit helper. Tighten with admin scope before production money movement."""
    return wallet_service.post_ledger_entry(
        principal,
        user_id,
        amount_mru=body.amount_mru,
        kind=body.kind,
        reference=body.reference,
        note=body.note,
        idempotency_key=body.idempotency_key,
    )
