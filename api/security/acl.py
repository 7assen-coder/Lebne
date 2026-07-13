"""Roles, scopes, and action → permission mapping."""

from __future__ import annotations

from enum import Enum

from api.schemas import AccountActionType, Sensitivity


class Role(str, Enum):
    END_USER = "end_user"
    SUPPORT_AGENT = "support_agent"
    ADMIN = "admin"
    SERVICE = "service"


class Scope(str, Enum):
    CHAT = "chat:write"
    BALANCE_READ = "wallet:balance:read"
    TX_READ = "wallet:transactions:read"
    PROFILE_WRITE = "wallet:profile:write"
    PASSWORD_WRITE = "wallet:password:write"
    PHONE_WRITE = "wallet:phone:write"
    AUDIT_READ = "audit:read"


ROLE_DEFAULT_SCOPES: dict[Role, frozenset[Scope]] = {
    Role.END_USER: frozenset(
        {
            Scope.CHAT,
            Scope.BALANCE_READ,
            Scope.TX_READ,
            Scope.PROFILE_WRITE,
            Scope.PASSWORD_WRITE,
            Scope.PHONE_WRITE,
        }
    ),
    Role.SUPPORT_AGENT: frozenset({Scope.CHAT, Scope.AUDIT_READ}),
    Role.ADMIN: frozenset(Scope),
    Role.SERVICE: frozenset(
        {
            Scope.BALANCE_READ,
            Scope.TX_READ,
            Scope.PROFILE_WRITE,
            Scope.PASSWORD_WRITE,
            Scope.PHONE_WRITE,
        }
    ),
}


ACTION_REQUIRED_SCOPE: dict[AccountActionType, Scope] = {
    AccountActionType.GET_BALANCE: Scope.BALANCE_READ,
    AccountActionType.LIST_TRANSACTIONS: Scope.TX_READ,
    AccountActionType.UPDATE_PROFILE: Scope.PROFILE_WRITE,
    AccountActionType.CHANGE_PASSWORD: Scope.PASSWORD_WRITE,
    AccountActionType.CHANGE_PHONE: Scope.PHONE_WRITE,
}


ACTION_SENSITIVITY: dict[AccountActionType, Sensitivity] = {
    AccountActionType.GET_BALANCE: Sensitivity.AUTHENTICATED,
    AccountActionType.LIST_TRANSACTIONS: Sensitivity.AUTHENTICATED,
    AccountActionType.UPDATE_PROFILE: Sensitivity.CONFIRMATION,
    AccountActionType.CHANGE_PASSWORD: Sensitivity.STRONG_2FA,
    AccountActionType.CHANGE_PHONE: Sensitivity.STRONG_2FA,
}


def scopes_for_roles(roles: list[Role] | list[str]) -> set[str]:
    out: set[str] = set()
    for role in roles:
        role_enum = role if isinstance(role, Role) else Role(role)
        out.update(s.value for s in ROLE_DEFAULT_SCOPES.get(role_enum, frozenset()))
    return out
