"""JWT authentication — never trust client-supplied user_id.

Supports local HS256 (dev) and real IdP JWKS (OIDC) verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.config import Settings, get_settings
from api.security.acl import Role, Scope, scopes_for_roles
from api.security.oidc import decode_oidc_token, roles_and_scopes_from_oidc

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: str
    roles: tuple[str, ...]
    scopes: frozenset[str]
    token_jti: str | None = None
    auth_source: str = "local"

    def has_scope(self, scope: Scope | str) -> bool:
        value = scope.value if isinstance(scope, Scope) else scope
        return value in self.scopes

    def require_scope(self, scope: Scope | str) -> None:
        if not self.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {scope}",
            )


def mint_access_token(
    *,
    user_id: str,
    roles: list[str] | None = None,
    scopes: list[str] | None = None,
    settings: Settings | None = None,
    ttl_seconds: int | None = None,
) -> str:
    settings = settings or get_settings()
    if settings.env == "production" and settings.auth_mode == "oidc":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local token mint disabled in production OIDC mode",
        )
    role_list = roles or [Role.END_USER.value]
    scope_set = set(scopes) if scopes is not None else scopes_for_roles(role_list)
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user_id,
        "roles": role_list,
        "scopes": sorted(scope_set),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds or settings.access_token_ttl_seconds)).timestamp()),
        "jti": f"access-{user_id}-{int(now.timestamp())}",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def mint_service_token(
    *,
    scopes: list[str],
    settings: Settings | None = None,
    subject: str = "lebne-agent",
) -> str:
    """Least-privilege token for agent → wallet calls (split-deploy mode)."""
    settings = settings or get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "roles": [Role.SERVICE.value],
        "scopes": scopes,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=300)).timestamp()),
        "jti": f"svc-{subject}-{int(now.timestamp())}",
        "token_use": "service",
    }
    return jwt.encode(payload, settings.service_jwt_secret, algorithm=settings.jwt_algorithm)


def decode_local_token(token: str, settings: Settings, *, service: bool = False) -> dict[str, Any]:
    secret = settings.service_jwt_secret if service else settings.jwt_secret
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc


# Backward-compatible alias used by tests
decode_token = decode_local_token


def principal_from_payload(payload: dict[str, Any], *, auth_source: str = "local") -> Principal:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject")
    if auth_source == "oidc":
        roles, scopes = roles_and_scopes_from_oidc(payload)
    else:
        roles = list(payload.get("roles") or [])
        scopes = payload.get("scopes")
        if scopes is None:
            scopes = scopes_for_roles(roles or [Role.END_USER.value])
        else:
            scopes = set(scopes)
        roles = roles or [Role.END_USER.value]
    return Principal(
        user_id=str(user_id),
        roles=tuple(roles),
        scopes=frozenset(scopes),
        token_jti=payload.get("jti"),
        auth_source=auth_source,
    )


def decode_user_token(token: str, settings: Settings) -> Principal:
    """Decode a user access token according to auth_mode."""
    mode = settings.auth_mode
    if settings.env == "production" and mode == "local" and not settings.oidc_jwks_url:
        # Still allow local in misconfigured prod, but prefer OIDC when URL is set.
        pass

    errors: list[str] = []

    if mode in {"oidc", "hybrid"} and settings.oidc_jwks_url:
        try:
            payload = decode_oidc_token(token, settings)
            return principal_from_payload(payload, auth_source="oidc")
        except HTTPException as exc:
            errors.append(str(exc.detail))
            if mode == "oidc":
                raise

    if mode in {"local", "hybrid"}:
        # Production OIDC-only: do not accept local user HS256.
        if settings.env == "production" and mode == "oidc":
            raise HTTPException(status_code=401, detail="Local user tokens disabled")
        if settings.env == "production" and mode == "hybrid" and settings.oidc_jwks_url and errors:
            # hybrid in prod: allow local only if explicitly hybrid (staging-like)
            pass
        try:
            payload = decode_local_token(token, settings, service=False)
            if payload.get("token_use") == "service":
                raise HTTPException(status_code=401, detail="Service token not valid for user routes")
            return principal_from_payload(payload, auth_source="local")
        except HTTPException as exc:
            errors.append(str(exc.detail))

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="; ".join(errors) or "Unauthorized",
    )


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if not settings.require_auth:
        return Principal(
            user_id="dev-anonymous",
            roles=(Role.END_USER.value,),
            scopes=frozenset(scopes_for_roles([Role.END_USER])),
            auth_source="dev",
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")

    token = credentials.credentials
    try:
        return decode_user_token(token, settings)
    except HTTPException:
        # Service token path (agent → wallet HTTP)
        payload = decode_local_token(token, settings, service=True)
        return principal_from_payload(payload, auth_source="service")
