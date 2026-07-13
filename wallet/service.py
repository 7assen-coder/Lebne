"""Wallet service — ACL + Postgres/SQLite persistence. No LLM DB access."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import AccountActionType
from api.security.acl import ACTION_REQUIRED_SCOPE
from api.security.audit import audit_logger
from api.security.auth import Principal
from wallet.db import get_session_factory
from wallet.models import LedgerEntry, UserAccount


class WalletService:
    """Authoritative wallet ops. Agent and Flutter both go through this."""

    def _session(self) -> Session:
        return get_session_factory()()

    def _authorize(self, principal: Principal, action: AccountActionType, resource_user_id: str) -> None:
        if "service" not in principal.roles and principal.user_id != resource_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access another user's wallet",
            )
        principal.require_scope(ACTION_REQUIRED_SCOPE[action])

    def _get_or_create_user(self, session: Session, user_id: str) -> UserAccount:
        user = session.get(UserAccount, user_id)
        if user is None:
            user = UserAccount(user_id=user_id, display_name="Lebne User", balance_mru=0)
            session.add(user)
            session.flush()
        return user

    def get_balance(self, principal: Principal, user_id: str) -> dict[str, Any]:
        self._authorize(principal, AccountActionType.GET_BALANCE, user_id)
        session = self._session()
        try:
            user = self._get_or_create_user(session, user_id)
            session.commit()
            balance = user.balance_mru
        finally:
            session.close()
        audit_logger.record(
            user_id=user_id,
            action="get_balance",
            outcome="ok",
            principal_roles=list(principal.roles),
        )
        return {"user_id": user_id, "balance_mru": balance, "currency": "MRU"}

    def list_transactions(self, principal: Principal, user_id: str) -> dict[str, Any]:
        self._authorize(principal, AccountActionType.LIST_TRANSACTIONS, user_id)
        session = self._session()
        try:
            self._get_or_create_user(session, user_id)
            rows = session.scalars(
                select(LedgerEntry)
                .where(LedgerEntry.user_id == user_id)
                .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
                .limit(100)
            ).all()
            session.commit()
            transactions = [
                {
                    "id": row.id,
                    "amount_mru": row.amount_mru,
                    "kind": row.kind,
                    "reference": row.reference,
                    "note": row.note,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]
        finally:
            session.close()
        audit_logger.record(
            user_id=user_id,
            action="list_transactions",
            outcome="ok",
            principal_roles=list(principal.roles),
        )
        return {"user_id": user_id, "transactions": transactions}

    def update_profile(
        self, principal: Principal, user_id: str, display_name: str | None = None
    ) -> dict[str, Any]:
        self._authorize(principal, AccountActionType.UPDATE_PROFILE, user_id)
        session = self._session()
        try:
            user = self._get_or_create_user(session, user_id)
            if display_name:
                user.display_name = display_name
            name = user.display_name
            session.commit()
        finally:
            session.close()
        audit_logger.record(
            user_id=user_id,
            action="update_profile",
            outcome="ok",
            principal_roles=list(principal.roles),
        )
        return {"user_id": user_id, "display_name": name}

    def change_password(self, principal: Principal, user_id: str, new_password: str) -> dict[str, Any]:
        self._authorize(principal, AccountActionType.CHANGE_PASSWORD, user_id)
        from wallet.passwords import hash_password

        try:
            hashed = hash_password(new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session = self._session()
        try:
            user = self._get_or_create_user(session, user_id)
            user.password_hash = hashed
            session.commit()
        finally:
            session.close()
        audit_logger.record(
            user_id=user_id,
            action="change_password",
            outcome="ok",
            principal_roles=list(principal.roles),
            detail={"note": "argon2id hash updated"},
        )
        return {"user_id": user_id, "status": "password_updated"}

    def verify_user_password(self, user_id: str, password: str) -> bool:
        from wallet.passwords import needs_rehash, verify_password, hash_password

        session = self._session()
        try:
            user = session.get(UserAccount, user_id)
            if user is None:
                return False
            ok = verify_password(user.password_hash, password)
            if ok and needs_rehash(user.password_hash):
                user.password_hash = hash_password(password)
                session.commit()
            return ok
        finally:
            session.close()

    def ensure_user_with_password(self, user_id: str, password: str, display_name: str = "Lebne User") -> None:
        """Local registration helper (dev/hybrid). Not used when IdP owns identities."""
        from wallet.passwords import hash_password

        session = self._session()
        try:
            user = session.get(UserAccount, user_id)
            hashed = hash_password(password)
            if user is None:
                session.add(
                    UserAccount(
                        user_id=user_id,
                        display_name=display_name,
                        password_hash=hashed,
                        balance_mru=0,
                    )
                )
            else:
                user.password_hash = hashed
            session.commit()
        finally:
            session.close()

    def change_phone(self, principal: Principal, user_id: str, new_phone: str) -> dict[str, Any]:
        self._authorize(principal, AccountActionType.CHANGE_PHONE, user_id)
        session = self._session()
        try:
            user = self._get_or_create_user(session, user_id)
            user.phone = new_phone
            session.commit()
        finally:
            session.close()
        audit_logger.record(
            user_id=user_id,
            action="change_phone",
            outcome="ok",
            principal_roles=list(principal.roles),
            detail={"phone_redacted": True},
        )
        return {"user_id": user_id, "status": "phone_updated"}

    def post_ledger_entry(
        self,
        principal: Principal,
        user_id: str,
        *,
        amount_mru: int,
        kind: str,
        reference: str = "",
        note: str = "",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Credit/debit with append-only ledger. Requires balance read scope for now
        (internal/admin path — tighten with a dedicated scope later)."""
        self._authorize(principal, AccountActionType.GET_BALANCE, user_id)
        if amount_mru == 0:
            raise HTTPException(status_code=400, detail="amount_mru must be non-zero")

        session = self._session()
        try:
            if idempotency_key:
                existing = session.scalars(
                    select(LedgerEntry).where(LedgerEntry.idempotency_key == idempotency_key)
                ).first()
                if existing:
                    user = self._get_or_create_user(session, user_id)
                    session.commit()
                    return {
                        "user_id": user_id,
                        "balance_mru": user.balance_mru,
                        "entry_id": existing.id,
                        "idempotent_replay": True,
                    }

            user = self._get_or_create_user(session, user_id)
            new_balance = user.balance_mru + amount_mru
            if new_balance < 0:
                raise HTTPException(status_code=400, detail="Insufficient balance")
            entry = LedgerEntry(
                user_id=user_id,
                amount_mru=amount_mru,
                kind=kind,
                reference=reference,
                note=note,
                idempotency_key=idempotency_key,
            )
            user.balance_mru = new_balance
            session.add(entry)
            session.commit()
            session.refresh(entry)
            entry_id = entry.id
            balance = user.balance_mru
        finally:
            session.close()

        audit_logger.record(
            user_id=user_id,
            action="ledger_post",
            outcome="ok",
            principal_roles=list(principal.roles),
            detail={"kind": kind, "amount_mru": amount_mru},
        )
        return {
            "user_id": user_id,
            "balance_mru": balance,
            "entry_id": entry_id,
            "idempotent_replay": False,
        }


wallet_service = WalletService()
