"""JWT helpers for crowd contributors (separate audience from wallet tokens)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.config import Settings, get_settings
from contrib.db import get_contrib_session
from contrib.models import ROLE_OWNER, ROLE_REVIEWER, CrowdUser

CROWD_AUD = "lebne-crowd"


def effective_role(user: CrowdUser) -> str:
    role = (user.role or "").strip().lower()
    if role in ("owner", "reviewer", "contributor"):
        return role
    # Legacy fallback
    return ROLE_OWNER if user.is_admin else "contributor"


def mint_crowd_token(user: CrowdUser, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    role = effective_role(user)
    ttl_days = max(1, min(int(settings.crowd_token_ttl_days or 7), 30))
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "role": role,
        "is_admin": role == ROLE_OWNER,
        "tv": int(getattr(user, "token_version", 0) or 0),
        "iss": settings.jwt_issuer,
        "aud": CROWD_AUD,
        "iat": now,
        "exp": now + timedelta(days=ttl_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_crowd_user(
    request: Request,
    db: Annotated[Session, Depends(get_contrib_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CrowdUser:
    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login required")
    token = auth.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=CROWD_AUD,
            issuer=settings.jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    user_id = int(payload.get("sub") or 0)
    user = db.get(CrowdUser, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    token_tv = int(payload.get("tv") or 0)
    current_tv = int(getattr(user, "token_version", 0) or 0)
    if token_tv != current_tv:
        raise HTTPException(status_code=401, detail="Session revoked — please log in again")
    return user


def require_owner(user: Annotated[CrowdUser, Depends(get_crowd_user)]) -> CrowdUser:
    if effective_role(user) != ROLE_OWNER:
        raise HTTPException(status_code=403, detail="Owner only")
    return user


def require_reviewer_or_owner(user: Annotated[CrowdUser, Depends(get_crowd_user)]) -> CrowdUser:
    if effective_role(user) not in (ROLE_OWNER, ROLE_REVIEWER):
        raise HTTPException(status_code=403, detail="Reviewer or owner only")
    return user


# Back-compat alias used by any leftover imports
def require_crowd_admin(user: Annotated[CrowdUser, Depends(get_crowd_user)]) -> CrowdUser:
    return require_reviewer_or_owner(user)
