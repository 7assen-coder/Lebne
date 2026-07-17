"""FastAPI entrypoint — JWT auth, wallet routes, step-up security."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from agent.graph import run_agent
from api.config import Settings, get_settings
from api.logging_utils import get_logger, redact
from api.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ConfirmChallengeRequest,
    DevTokenRequest,
    LoginRequest,
    RegisterRequest,
    TwoFAVerifyRequest,
)
from api.security.acl import Scope
from api.security.audit import audit_logger
from api.security.auth import Principal, get_current_principal, mint_access_token
from api.security.chat_safety import sanitize_user_text
from api.security.rate_limit import enforce_rate_limit
from api.security.step_up import issue_confirmation, peek_dev_2fa_code, verify_two_fa
from api.session import session_store
from contrib.api_v1 import router as crowd_api_router
from contrib.db import init_contrib_db
from contrib.routes import router as contrib_router
from wallet.db import init_db
from wallet.routes import router as wallet_router
from wallet.service import wallet_service

_settings = get_settings()
_crowd_only = bool(_settings.crowd_surface_only)
_is_prod = _settings.env == "production"

app = FastAPI(
    title="Lebne Crowd API" if _crowd_only else "Lebne Agent + Wallet API",
    version="0.4.0",
    # Hide interactive docs on public production surfaces
    docs_url=None if (_is_prod or _crowd_only) else "/docs",
    redoc_url=None if (_is_prod or _crowd_only) else "/redoc",
    openapi_url=None if (_is_prod or _crowd_only) else "/openapi.json",
)
_origins = [o.strip() for o in (_settings.cors_origins or "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "microphone=(self), camera=(), geolocation=()",
    )
    response.headers.setdefault("X-XSS-Protection", "0")
    if _is_prod or _crowd_only:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=63072000; includeSubDomains; preload",
        )
    return response


@app.middleware("http")
async def crowd_surface_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Block wallet/chat/legacy paths when the public API is crowd-only (Render)."""
    if _crowd_only:
        path = request.url.path or "/"
        allowed = (
            path == "/"
            or path == "/health"
            or path.startswith("/crowd/v1")
        )
        if not allowed:
            return JSONResponse({"detail": "Not found"}, status_code=404)
    return await call_next(request)


# Crowd API is always mounted. Wallet/legacy only when not in crowd-surface mode.
if not _crowd_only:
    app.include_router(wallet_router)
    app.include_router(contrib_router)
    _contrib_static = Path(__file__).resolve().parents[1] / "contrib" / "static"
    app.mount("/contrib/static", StaticFiles(directory=str(_contrib_static)), name="contrib_static")
app.include_router(crowd_api_router)
log = get_logger("api")


@app.on_event("startup")
async def on_startup() -> None:
    settings = get_settings()
    # Crowd-only public hosts still need contrib tables; skip wallet init noise when possible.
    if not settings.crowd_surface_only:
        init_db()
    init_contrib_db()
    Path("media/contrib_audio").mkdir(parents=True, exist_ok=True)
    if settings.env == "production":
        weak = ("CHANGE_ME", "dev_only", "lebne_jwt_secret")
        secret = settings.jwt_secret or ""
        if any(m in secret for m in weak) or len(secret) < 32:
            raise RuntimeError("Production requires a strong LEBNE_JWT_SECRET (>=32 chars)")
        if settings.auth_mode == "oidc" and not settings.oidc_jwks_url:
            raise RuntimeError("Production OIDC mode requires LEBNE_OIDC_JWKS_URL")
        if settings.contrib_legacy_enabled:
            raise RuntimeError("Disable LEBNE_CONTRIB_LEGACY_ENABLED in production (use /crowd/v1)")
        origins = [o.strip() for o in (settings.cors_origins or "").split(",") if o.strip()]
        if not origins or "*" in origins:
            raise RuntimeError("Production requires an explicit LEBNE_CORS_ORIGINS allowlist")
    if settings.contrib_legacy_enabled and settings.contrib_admin_password in {
        "",
        "CHANGE_ME_CONTRIB_ADMIN",
    }:
        raise RuntimeError(
            "LEBNE_CONTRIB_LEGACY_ENABLED requires a strong LEBNE_CONTRIB_ADMIN_PASSWORD"
        )
    try:
        from contrib.export_util import scrub_all_locale_files

        # Marker-gated: runs once, not on every container restart
        scrub_all_locale_files()
    except OSError:
        pass
    log.info(
        "db_ready",
        msg="wallet tables ensured",
        auth_mode=settings.auth_mode,
        env=settings.env,
        contrib_legacy=settings.contrib_legacy_enabled,
    )


@app.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "status": "ok",
        "service": "lebne",
        "auth_mode": settings.auth_mode,
        "env": settings.env,
    }


@app.post("/v1/auth/dev-token")
async def dev_token(body: DevTokenRequest, settings: Settings = Depends(get_settings)) -> dict[str, str]:
    """Mint a JWT for local/dev only. Disabled in production and in oidc-only mode."""
    if settings.env == "production" or settings.auth_mode == "oidc":
        raise HTTPException(status_code=404, detail="Not found")
    token = mint_access_token(user_id=body.user_id, roles=body.roles, settings=settings)
    return {"access_token": token, "token_type": "bearer"}


@app.post("/v1/auth/register")
async def register(body: RegisterRequest, settings: Settings = Depends(get_settings)) -> dict[str, str]:
    """Local account registration with argon2. Disabled in production OIDC mode."""
    if settings.env == "production" and settings.auth_mode == "oidc":
        raise HTTPException(status_code=404, detail="Not found — use IdP registration")
    if settings.auth_mode == "oidc":
        raise HTTPException(status_code=403, detail="Local registration disabled in OIDC mode")
    wallet_service.ensure_user_with_password(body.user_id, body.password, body.display_name)
    token = mint_access_token(user_id=body.user_id, roles=["end_user"], settings=settings)
    return {"access_token": token, "token_type": "bearer"}


@app.post("/v1/auth/login")
async def login(body: LoginRequest, settings: Settings = Depends(get_settings)) -> dict[str, str]:
    """Local password login (argon2 verify → JWT). Prefer IdP in production."""
    if settings.auth_mode == "oidc":
        raise HTTPException(status_code=403, detail="Use IdP login; local password login disabled")
    if not wallet_service.verify_user_password(body.user_id, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = mint_access_token(user_id=body.user_id, roles=["end_user"], settings=settings)
    audit_logger.record(
        user_id=body.user_id,
        action="login",
        outcome="ok",
        principal_roles=["end_user"],
    )
    return {"access_token": token, "token_type": "bearer"}


@app.post("/v1/security/confirm")
async def create_confirmation(
    body: ConfirmChallengeRequest,
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict:
    challenge = issue_confirmation(
        user_id=principal.user_id,
        action=body.action,
        session_id=body.session_id,
        settings=settings,
    )
    out = {
        "confirmation_token": challenge.confirmation_token,
        "two_fa_required": challenge.two_fa_required,
        "two_fa_challenge_id": challenge.two_fa_challenge_id,
        "expires_in": challenge.expires_in,
    }
    if challenge.two_fa_challenge_id:
        code = peek_dev_2fa_code(challenge.two_fa_challenge_id, settings)
        if code:
            out["dev_2fa_code"] = code
    return out


@app.post("/v1/security/2fa/verify")
async def verify_2fa_endpoint(
    body: TwoFAVerifyRequest,
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    token = verify_two_fa(
        challenge_id=body.challenge_id,
        code=body.code,
        user_id=principal.user_id,
        action=body.action,
        settings=settings,
    )
    audit_logger.record(
        user_id=principal.user_id,
        action=f"2fa_verify:{body.action.value}",
        outcome="ok",
        principal_roles=list(principal.roles),
    )
    return {"two_fa_token": token}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    principal: Principal = Depends(get_current_principal),
) -> ChatResponse:
    principal.require_scope(Scope.CHAT)
    await enforce_rate_limit(request, principal.user_id, settings)

    # Know the user via JWT only. Scrub secrets before history persistence + logs.
    safe_in = sanitize_user_text(body.message)
    log.info(
        "chat_request",
        user_id=principal.user_id,
        session_id=body.session_id,
        message=redact(safe_in.safe_text),
        prompt_redactions=safe_in.redactions,
        injection_flags=safe_in.injection_flags,
    )

    session_store.append(
        principal.user_id,
        body.session_id,
        ChatMessage(role="user", content=safe_in.safe_text),
        settings,
    )
    state = session_store.get_or_create(principal.user_id, body.session_id, settings)

    result = await run_agent(
        principal=principal,
        session_id=body.session_id,
        message=safe_in.safe_text,
        history=state.messages,
        confirmation_token=body.confirmation_token,
        two_fa_token=body.two_fa_token,
        settings=settings,
    )

    session_store.append(
        principal.user_id,
        body.session_id,
        ChatMessage(role="assistant", content=result.reply),
        settings,
    )
    return result
