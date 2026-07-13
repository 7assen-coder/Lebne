"""Account actions agent — wallet only via ACL-controlled WalletService / HTTP."""

from __future__ import annotations

from typing import Any

import httpx

from api.config import Settings
from api.schemas import AccountActionType
from api.security.acl import ACTION_REQUIRED_SCOPE
from api.security.auth import Principal, mint_service_token
from wallet.service import wallet_service


class AccountActionsAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def detect_action(self, message: str) -> AccountActionType:
        lower = message.lower()
        if any(k in lower for k in ("password", "mot de passe", "كلمة")):
            return AccountActionType.CHANGE_PASSWORD
        if any(k in lower for k in ("phone", "numéro", "رقم")):
            return AccountActionType.CHANGE_PHONE
        if any(k in lower for k in ("historique", "history", "transactions")):
            return AccountActionType.LIST_TRANSACTIONS
        if any(k in lower for k in ("solde", "balance", "رصيد")):
            return AccountActionType.GET_BALANCE
        return AccountActionType.UPDATE_PROFILE

    async def execute(
        self,
        *,
        action: AccountActionType,
        user_id: str,
        principal: Principal,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute via in-process wallet (preferred) or scoped HTTP service token."""
        payload = payload or {}

        if self.settings.wallet_internal_mode:
            # Act as end-user principal for ownership checks; scopes already on JWT.
            if action == AccountActionType.GET_BALANCE:
                data = wallet_service.get_balance(principal, user_id)
            elif action == AccountActionType.LIST_TRANSACTIONS:
                data = wallet_service.list_transactions(principal, user_id)
            elif action == AccountActionType.UPDATE_PROFILE:
                data = wallet_service.update_profile(principal, user_id, payload.get("display_name"))
            elif action == AccountActionType.CHANGE_PASSWORD:
                data = wallet_service.change_password(principal, user_id, payload.get("new_password", "ChangeMe123"))
            elif action == AccountActionType.CHANGE_PHONE:
                data = wallet_service.change_phone(principal, user_id, payload.get("new_phone", "+22200000000"))
            else:
                data = {"status": "unknown_action"}
            return {"reply": f"Action `{action.value}` completed.", "metadata": {"wallet": data}}

        scope = ACTION_REQUIRED_SCOPE[action].value
        token = mint_service_token(scopes=[scope], settings=self.settings)
        path_map = {
            AccountActionType.GET_BALANCE: f"/wallet/v1/users/{user_id}/balance",
            AccountActionType.LIST_TRANSACTIONS: f"/wallet/v1/users/{user_id}/transactions",
            AccountActionType.CHANGE_PASSWORD: f"/wallet/v1/users/{user_id}/password",
            AccountActionType.CHANGE_PHONE: f"/wallet/v1/users/{user_id}/phone",
            AccountActionType.UPDATE_PROFILE: f"/wallet/v1/users/{user_id}/profile",
        }
        url = f"{self.settings.backend_api_base_url.rstrip('/')}{path_map[action]}"
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            if action in {AccountActionType.GET_BALANCE, AccountActionType.LIST_TRANSACTIONS}:
                response = await client.get(url, headers=headers)
            else:
                response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return {"reply": f"Action `{action.value}` completed.", "metadata": {"wallet": response.json()}}
