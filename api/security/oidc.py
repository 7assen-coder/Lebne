"""OIDC / IdP JWT verification via JWKS (Keycloak, Auth0, Cognito, etc.)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import jwt
from fastapi import HTTPException, status
from jwt import PyJWKClient

from api.config import Settings
from api.security.acl import Role, scopes_for_roles


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True)


def decode_oidc_token(token: str, settings: Settings) -> dict[str, Any]:
    if not settings.oidc_jwks_url:
        raise HTTPException(status_code=401, detail="OIDC JWKS not configured")
    try:
        client = _jwks_client(settings.oidc_jwks_url)
        key = client.get_signing_key_from_jwt(token)
        algorithms = settings.oidc_algorithms.split(",")
        options = {"verify_aud": bool(settings.oidc_audience)}
        payload = jwt.decode(
            token,
            key.key,
            algorithms=[a.strip() for a in algorithms if a.strip()],
            audience=settings.oidc_audience or None,
            issuer=settings.oidc_issuer or None,
            options=options,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired IdP token",
        ) from exc
    return payload


def roles_and_scopes_from_oidc(payload: dict[str, Any]) -> tuple[list[str], set[str]]:
    """Map common IdP claim shapes to Lebne roles/scopes."""
    roles: list[str] = []
    if "roles" in payload and isinstance(payload["roles"], list):
        roles = [str(r) for r in payload["roles"]]
    elif isinstance(payload.get("realm_access"), dict):
        roles = [str(r) for r in payload["realm_access"].get("roles", [])]
    # Normalize unknown IdP roles to end_user unless admin/support appear.
    normalized: list[str] = []
    for r in roles:
        rl = r.lower()
        if rl in {Role.ADMIN.value, "admin"}:
            normalized.append(Role.ADMIN.value)
        elif rl in {Role.SUPPORT_AGENT.value, "support", "support_agent"}:
            normalized.append(Role.SUPPORT_AGENT.value)
        elif rl in {Role.END_USER.value, "user", "end_user", "default-roles-lebne"}:
            normalized.append(Role.END_USER.value)
    if not normalized:
        normalized = [Role.END_USER.value]

    scopes: set[str] = set()
    raw_scope = payload.get("scope") or payload.get("scp")
    if isinstance(raw_scope, str):
        scopes.update(raw_scope.split())
    elif isinstance(raw_scope, list):
        scopes.update(str(s) for s in raw_scope)
    if "scopes" in payload and isinstance(payload["scopes"], list):
        scopes.update(str(s) for s in payload["scopes"])
    if not scopes:
        scopes = scopes_for_roles(normalized)
    return normalized, scopes
